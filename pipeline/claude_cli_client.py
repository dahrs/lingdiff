"""Calls an LLM by shelling out to the real `claude` CLI in `-p`/print (non-interactive)
mode, instead of a separate pay-per-token `ANTHROPIC_API_KEY` — reuses the OAuth session a
`claude login`'d Claude Pro/Max subscription already has. Same approach and mechanics as
ye_olde's `common/claude_cli_client.py`; trimmed here since lingdiff only ever calls this one
backend (no litellm multi-provider dispatch layer to adapt to).

**Decisions carried over from that module, still true here:**
- Shares the interactive Claude Code session's usage window — fine for this pipeline's
  per-language batch calls (not a high-volume production service).
- `--restricted --disable-slash-commands` plus a neutral `cwd`: narrows the gap to a plain
  API call (no Bash/WebFetch/code-exec tools, no CLAUDE.md/skill auto-discovery bleeding in
  from whatever repo the caller lives in) without forcing API-key-only auth the way `--bare`
  would.
- The prompt is piped via stdin, never passed as a `claude -p <prompt>` argument — argv has a
  kernel-enforced size limit (`ARG_MAX`) that a Wikipedia-extract-sized prompt can exceed.
- A usage-limit/overload failure (recognizable by substring match) is retried forever with a
  logged wait, rather than raised — an expected, recoverable condition for this backend
  specifically. Every other failure raises immediately.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import time
from typing import Any

from pydantic import BaseModel

from pipeline.errors import LLMEmptyResponseError, LLMNotConfiguredError

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 600.0
_USAGE_LIMIT_RETRY_SECONDS = 3600.0

_USAGE_LIMIT_MARKERS = (
    "usage limit reached",
    "session limit",
    "credit balance too low",
    "rate limited",
    "overloaded",
    "529",
)


def _is_usage_limit_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _USAGE_LIMIT_MARKERS)


class ClaudeCliCompletion(BaseModel):
    content: str
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def complete_via_claude_cli(
    prompt: str,
    *,
    system: str | None = None,
    model: str = "claude-sonnet-5",
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    usage_limit_retry_seconds: float = _USAGE_LIMIT_RETRY_SECONDS,
) -> ClaudeCliCompletion:
    """Runs `claude -p --output-format json` and returns the parsed result, retrying
    forever (sleeping `usage_limit_retry_seconds` between attempts) on a usage-limit/overload
    failure. Raises `LLMNotConfiguredError` if `claude` isn't on PATH, `LLMEmptyResponseError`
    for any other failure (nonzero exit, timeout, non-JSON stdout, `is_error: true`)."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--restricted", "--disable-slash-commands"]
    if system:
        cmd += ["--append-system-prompt", system]

    while True:
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),
            )
        except FileNotFoundError as exc:
            raise LLMNotConfiguredError("the `claude` binary isn't on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMEmptyResponseError(f"claude -p did not finish within {timeout}s") from exc

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        payload: dict[str, Any] | None = None
        parse_exc: json.JSONDecodeError | None = None
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError as exc:
                parse_exc = exc

        if payload is None:
            if proc.returncode != 0:
                if _is_usage_limit_message(stderr) or (not stderr and not stdout):
                    _wait_out_usage_limit(stderr or "(no output on either stream)", usage_limit_retry_seconds)
                    continue
                raise LLMEmptyResponseError(
                    f"claude -p exited {proc.returncode}: {stderr[:500]} | stdout: {stdout[:500]}"
                )
            raise LLMEmptyResponseError(
                f"claude -p produced non-JSON --output-format=json output: {parse_exc}"
            ) from parse_exc

        if payload.get("is_error") or proc.returncode != 0:
            message = str(payload.get("result") or payload.get("subtype") or "")
            if _is_usage_limit_message(message) or not message:
                _wait_out_usage_limit(
                    message or f"(structured reply carried no error message, exit code {proc.returncode})",
                    usage_limit_retry_seconds,
                )
                continue
            raise LLMEmptyResponseError(f"claude -p reported an error: {message}")

        return _to_completion(payload)


def _wait_out_usage_limit(message: str, retry_seconds: float) -> None:
    log.info("claude -p hit a usage limit/overload, waiting %.0fs before retrying: %s", retry_seconds, message[:300])
    print(
        f"[claude-cli] usage limit/overload hit, waiting {retry_seconds / 3600:.2f}h before retrying: {message[:300]}",
        file=sys.stderr,
        flush=True,
    )
    time.sleep(retry_seconds)


def _to_completion(payload: dict[str, Any]) -> ClaudeCliCompletion:
    usage = payload.get("usage") or {}
    prompt_tokens = (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
    )
    finish_reason = "length" if payload.get("stop_reason") == "max_tokens" else None
    return ClaudeCliCompletion(
        content=str(payload.get("result") or ""),
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=int(usage.get("output_tokens") or 0),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
    )
