"""Logging setup for this service — deliberately its own, separate from `pipeline`'s (see
data_loader.py's docstring for why this service doesn't depend on `pipeline` at all). Logs to
stdout rather than a local rotating file: unlike the pipeline (a long-running local script on
one machine), this is meant to run under whatever hosting platform the user deploys it to
(Render, Fly.io, a plain VM, ...), and those all capture stdout as the log by default — a
local file here would just be one more thing to go find on whichever machine happens to be
running it.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        _CONFIGURED = True
    return logging.getLogger(name)
