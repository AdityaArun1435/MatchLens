"""Generate -> validate -> retry once with the errors -> drop invalid parts -> template fallback."""
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from .. import config
from ..llm import LLMError, LLMProvider
from ..service import ProcessedMatch
from . import cache, prompts
from .context import Context, build_context
from .fallback import fallback_explanation, fallback_recap, fallback_title
from .models import (
    AttemptReport,
    DroppedItem,
    ExplainResult,
    MomentExplanation,
    Recap,
    RecapParagraph,
    RecapRequest,
    RecapResult,
    ValidationReport,
    explain_schema,
    recap_schema,
)
from .validate import Validator, strip_ids

MAX_ATTEMPTS = 2  # first try + one retry


class _RawParagraph(BaseModel):
    text: str
    cites: list[str]


class _RawRecap(BaseModel):
    title: str
    paragraphs: list[_RawParagraph]


class _RawExplanation(BaseModel):
    moment_id: str
    why_it_mattered: str
    context: str
    cites: list[str]


@dataclass
class _Attempt:
    report: AttemptReport
    title: str = ""
    title_errors: list[str] = field(default_factory=list)
    items: list[tuple[int, str, list[str], list[str]]] = field(default_factory=list)  # (index, text, cites, errors)
    notes: list[str] = field(default_factory=list)

    @property
    def valid(self) -> list[tuple[int, str, list[str], list[str]]]:
        return [i for i in self.items if not i[3]]


def _retry_prompt(user: str, errors: list[str]) -> str:
    listing = "\n".join(f"- {e}" for e in errors)
    return user + "\n\n" + prompts.render(prompts.load("retry"), errors=listing)


def _call(provider: LLMProvider, system: str, user: str, schema: dict, attempt_no: int):
    """Run one model call. LLMUnavailable propagates; other failures become an attempt report."""
    try:
        return provider.generate_json(system, user, schema), None
    except LLMError as exc:
        from ..llm import LLMUnavailable

        if isinstance(exc, LLMUnavailable):
            raise
        return None, AttemptReport(attempt=attempt_no, errors=[], llm_error=str(exc))


# ---- recap -----------------------------------------------------------------------------------------
def _recap_attempt(data, validator: Validator, attempt_no: int) -> _Attempt:
    try:
        raw = _RawRecap.model_validate(data)
    except ValidationError as exc:
        return _Attempt(AttemptReport(attempt=attempt_no, llm_error=f"output did not match the schema: {exc.errors()[0]['msg']}"))
    att = _Attempt(AttemptReport(attempt=attempt_no, items_total=len(raw.paragraphs)))
    att.title, _ = strip_ids(raw.title)
    att.title_errors = validator.check_title(att.title)
    errors = [f"Title: {e}" for e in att.title_errors]
    if not raw.paragraphs:
        errors.append("The answer contained no paragraphs.")
    for i, p in enumerate(raw.paragraphs, start=1):
        text, changed = strip_ids(p.text)
        if changed:
            att.notes.append(f"paragraph {i}: removed moment ids written inside the text")
        errs = validator.check_paragraph(text, p.cites)
        att.items.append((i, text, p.cites, errs))
        errors += [f"Paragraph {i}: {e}" for e in errs]
    att.report.items_valid = len(att.valid)
    att.report.errors = errors
    return att


def run_recap(
    match: ProcessedMatch,
    audience: str,
    length: str,
    language: str,
    provider: LLMProvider,
    *,
    min_importance: float | None = None,
) -> tuple[Recap, ValidationReport]:
    cutoff = config.RECAP_MIN_IMPORTANCE if min_importance is None else min_importance
    report = ValidationReport(method="llm")
    ctx = build_context(match, min_importance=cutoff)
    if not ctx.shown_ids:
        ctx = build_context(match, min_importance=0.0)
        report.notes.append(f"no moment reached importance {cutoff}; every moment was provided instead")
    if not ctx.shown_ids:
        report.method, report.fallback_reason = "fallback", "the match has no detected moments"
        return fallback_recap(match, length, cutoff), report

    validator = Validator(match, ctx)
    lo_hi = config.PARAGRAPHS_PER_LENGTH[length]
    system = prompts.load("system_base")
    user = prompts.render(
        prompts.load("recap_task"),
        context=ctx.text,
        audience=audience,
        audience_instructions=prompts.load(f"audience_{audience}"),
        length=length,
        length_instructions=prompts.load(f"length_{length}"),
        language_instructions=prompts.load(f"language_{language}"),
        ids=", ".join(ctx.shown_ids),
    )
    schema = recap_schema(ctx.shown_ids, length, lo_hi)

    attempts: list[_Attempt] = []
    prompt = user
    for n in range(1, MAX_ATTEMPTS + 1):
        data, failed = _call(provider, system, prompt, schema, n)
        att = _Attempt(failed) if failed else _recap_attempt(data, validator, n)
        attempts.append(att)
        report.attempts.append(att.report)
        report.notes += att.notes
        if att.report.llm_error is None and not att.report.errors:
            break
        if n < MAX_ATTEMPTS:
            problems = att.report.errors or [att.report.llm_error or "unusable answer"]
            prompt = _retry_prompt(user, problems)
    report.retried = len(attempts) > 1

    best = max(attempts, key=lambda a: (len(a.valid), a.report.attempt))  # ties go to the later attempt
    report.dropped = [DroppedItem(index=i, text=t, cites=c, errors=e) for i, t, c, e in best.items if e]
    if not best.valid:
        report.method = "fallback"
        report.fallback_reason = f"no valid paragraph after {len(attempts)} attempt(s)"
        return fallback_recap(match, length, cutoff), report
    title = best.title
    if best.title_errors or not title:
        title, report.title_replaced = fallback_title(match), True
    return Recap(title=title, paragraphs=[RecapParagraph(text=t, cites=c) for _, t, c, _ in best.valid]), report


# ---- explanation -----------------------------------------------------------------------------------
def _explain_attempt(data, validator: Validator, moment_id: str, attempt_no: int) -> tuple[AttemptReport, MomentExplanation | None]:
    try:
        raw = _RawExplanation.model_validate(data)
    except ValidationError as exc:
        return AttemptReport(attempt=attempt_no, llm_error=f"output did not match the schema: {exc.errors()[0]['msg']}"), None
    errors: list[str] = []
    if raw.moment_id != moment_id:
        errors.append(f"moment_id must be {moment_id}")
    why, _ = strip_ids(raw.why_it_mattered)
    ctx_text, _ = strip_ids(raw.context)
    errors += validator.check_cites(raw.cites, must_include=moment_id)
    errors += [f"why_it_mattered: {e}" for e in validator.check_text(why, raw.cites)]
    errors += [f"context: {e}" for e in validator.check_text(ctx_text, raw.cites)]
    report = AttemptReport(attempt=attempt_no, items_total=2, items_valid=0 if errors else 2, errors=errors)
    return report, MomentExplanation(moment_id=moment_id, why_it_mattered=why, context=ctx_text, cites=raw.cites)


def run_explanation(
    match: ProcessedMatch, moment_id: str, audience: str, language: str, provider: LLMProvider
) -> tuple[MomentExplanation, ValidationReport]:
    ctx: Context = build_context(match, min_importance=0.0, target=moment_id)
    report = ValidationReport(method="llm")
    validator = Validator(match, ctx)
    system = prompts.load("system_base")
    user = prompts.render(
        prompts.load("explain_task"),
        context=ctx.text,
        moment_id=moment_id,
        audience=audience,
        audience_instructions=prompts.load(f"audience_{audience}"),
        language_instructions=prompts.load(f"language_{language}"),
        ids=", ".join(ctx.shown_ids),
    )
    schema = explain_schema(ctx.shown_ids, moment_id)
    prompt, result = user, None
    for n in range(1, MAX_ATTEMPTS + 1):
        data, failed = _call(provider, system, prompt, schema, n)
        att, result = (failed, None) if failed else _explain_attempt(data, validator, moment_id, n)
        report.attempts.append(att)
        if att.llm_error is None and not att.errors:
            break
        result = None
        if n < MAX_ATTEMPTS:
            prompt = _retry_prompt(user, att.errors or [att.llm_error or "unusable answer"])
    report.retried = len(report.attempts) > 1
    if result is None:
        report.method = "fallback"
        report.fallback_reason = f"explanation still invalid after {len(report.attempts)} attempt(s)"
        return fallback_explanation(match, moment_id), report
    return result, report


# ---- cached entry points ---------------------------------------------------------------------------
def get_recap(match: ProcessedMatch, req: RecapRequest, provider: LLMProvider) -> RecapResult:
    path = cache.cache_file(
        "recap", match.meta.match_id, provider.name,
        audience=req.audience, length=req.length, language=req.language, cutoff=config.RECAP_MIN_IMPORTANCE,
    )
    if not req.refresh and (hit := cache.read(path, RecapResult)):
        return hit.model_copy(update={"cached": True})
    start = time.perf_counter()
    recap, report = run_recap(match, req.audience, req.length, req.language, provider)
    result = RecapResult(
        match_id=match.meta.match_id, audience=req.audience, length=req.length, language=req.language,
        model=provider.name, recap=recap, report=report, generation_seconds=round(time.perf_counter() - start, 2),
    )
    if report.method == "llm":  # never cache a fallback: the next call should try the model again
        cache.write(path, result)
    return result


def get_explanation(
    match: ProcessedMatch, moment_id: str, audience: str, language: str, provider: LLMProvider, refresh: bool = False
) -> ExplainResult:
    path = cache.cache_file(
        f"explain-{moment_id}", match.meta.match_id, provider.name, audience=audience, language=language
    )
    if not refresh and (hit := cache.read(path, ExplainResult)):
        return hit.model_copy(update={"cached": True})
    start = time.perf_counter()
    explanation, report = run_explanation(match, moment_id, audience, language, provider)
    result = ExplainResult(
        match_id=match.meta.match_id, moment_id=moment_id, audience=audience, language=language,
        model=provider.name, explanation=explanation, report=report,
        generation_seconds=round(time.perf_counter() - start, 2),
    )
    if report.method == "llm":
        cache.write(path, result)
    return result
