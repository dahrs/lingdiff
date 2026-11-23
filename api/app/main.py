"""lingdiff's comparison API: a thin HTTP wrapper around the same comparison logic
docs/compare.js runs in the browser (see diff.py), over the same precomputed profile data
the published site serves (see data_loader.py). Read-only, no state, no auth — the underlying
dataset is already public (CC-BY/CC0-licensed sources, see the main README's attribution
section).

Run locally: `uvicorn app.main:app --reload` from this directory.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.data_loader import ProfileStore
from app.diff import compare_languages
from app.logging_config import get_logger
from app.schemas import ComparisonResponse

log = get_logger(__name__)

app = FastAPI(
    title="lingdiff API",
    description="Compare two languages (by ISO 639-3 code or glottocode) across phonology, "
    "word order, morphology, writing system, family distance, and vocabulary origin.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_store = ProfileStore()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/compare", response_model=ComparisonResponse)
def compare(
    a: str = Query(
        ..., description="First language: ISO 639-3 code or glottocode, e.g. 'fra' or 'stan1290'"
    ),
    b: str = Query(..., description="Second language: ISO 639-3 code or glottocode"),
) -> ComparisonResponse:
    profile_a = _store.get(a)
    if profile_a is None:
        raise HTTPException(status_code=404, detail=f"Unknown language code: {a!r}")
    profile_b = _store.get(b)
    if profile_b is None:
        raise HTTPException(status_code=404, detail=f"Unknown language code: {b!r}")
    return compare_languages(profile_a, profile_b)


# Boundary layer: this is the only place in the service that catches a broad exception, and it
# always logs the full traceback before turning it into a generic response — a caught-and-
# handled error that isn't logged is invisible to whoever runs this later.
@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error handling %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "lingdiff API",
        "endpoints": {
            "GET /compare?a=<code>&b=<code>": "Full comparison between two languages",
            "GET /health": "Liveness check",
        },
        "docs": "/docs",
    }
