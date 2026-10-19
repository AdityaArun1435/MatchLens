"""FastAPI app. Run with: uvicorn matchlens.api:app --reload"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import loader, service
from .llm import LLMError, LLMProvider, LLMUnavailable, get_provider
from .models import Event, MatchSummary, Moment
from .recap import pipeline
from .recap.models import Audience, ExplainResult, Language, RecapRequest, RecapResult


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:  # warm the in-memory cache; the app still starts if data has not been fetched yet
        for entry in loader.load_index():
            service.get_match(entry["match_id"])
    except FileNotFoundError:
        pass
    yield


app = FastAPI(title="MatchLens", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _match(match_id: int) -> service.ProcessedMatch:
    try:
        return service.get_match(match_id)
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/matches")
def list_matches() -> list[dict]:
    try:
        entries = loader.load_index()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    out = []
    for entry in entries:
        m = service.get_match(entry["match_id"])
        out.append(
            {
                **m.meta.model_dump(),
                "went_to_extra_time": m.summary.went_to_extra_time,
                "shootout_winner": (m.summary.shootout or {}).get("winner"),
                "moment_count": len(m.moments),
            }
        )
    return out


@app.get("/matches/{match_id}/summary", response_model=MatchSummary)
def match_summary(match_id: int) -> MatchSummary:
    return _match(match_id).summary


@app.get("/matches/{match_id}/moments", response_model=list[Moment])
def match_moments(match_id: int, min_importance: float = Query(0.0, ge=0, le=1)) -> list[Moment]:
    return [m for m in _match(match_id).moments if m.importance >= min_importance]


@app.get("/matches/{match_id}/events", response_model=list[Event])
def match_events(
    match_id: int,
    from_minute: int | None = Query(None, ge=0),
    to_minute: int | None = Query(None, ge=0),
    period: int | None = Query(None, ge=1, le=5),
) -> list[Event]:
    """Events in match order. Minutes are StatsBomb elapsed minutes (inclusive) and repeat across a
    period boundary (stoppage time of period 1 overlaps the start of period 2), so add `period` to disambiguate."""
    return [
        e
        for e in _match(match_id).events
        if (from_minute is None or e.minute >= from_minute)
        and (to_minute is None or e.minute <= to_minute)
        and (period is None or e.period == period)
    ]


# ---- Phase 2: grounded recaps and explanations ---------------------------------------------------------
def provider_dep() -> LLMProvider:
    """The configured LLM provider. Tests override this dependency with a FakeProvider."""
    return get_provider()


def _llm_errors(exc: LLMError) -> HTTPException:
    if isinstance(exc, LLMUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@app.post("/matches/{match_id}/recap", response_model=RecapResult)
def make_recap(match_id: int, req: RecapRequest | None = None, provider: LLMProvider = Depends(provider_dep)) -> RecapResult:
    """Recap built only from the match summary and moments; the response includes the validation report."""
    match = _match(match_id)
    try:
        return pipeline.get_recap(match, req or RecapRequest(), provider)
    except LLMError as exc:
        raise _llm_errors(exc) from exc


@app.get("/matches/{match_id}/moments/{moment_id}/explain", response_model=ExplainResult)
def explain_moment(
    match_id: int,
    moment_id: str,
    audience: Audience = "analyst",
    language: Language = "en",
    refresh: bool = False,
    provider: LLMProvider = Depends(provider_dep),
) -> ExplainResult:
    match = _match(match_id)
    if moment_id not in {m.id for m in match.moments}:
        raise HTTPException(status_code=404, detail=f"match {match_id} has no moment {moment_id}")
    try:
        return pipeline.get_explanation(match, moment_id, audience, language, provider, refresh)
    except LLMError as exc:
        raise _llm_errors(exc) from exc
