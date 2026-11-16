"""Domain exceptions for the LLM-enrichment step — raised when enrich_llm.py's boundary
(run_pipeline.py's main()) needs to distinguish "the claude CLI isn't usable" from "a reply
came back malformed" from an arbitrary bug."""

from __future__ import annotations


class LLMNotConfiguredError(Exception):
    """The `claude` CLI binary isn't on PATH, or isn't authenticated."""


class LLMEmptyResponseError(Exception):
    """A `claude -p` call returned no usable content (empty, non-JSON output, or an
    error payload) for a reason that isn't a usage-limit/overload condition."""
