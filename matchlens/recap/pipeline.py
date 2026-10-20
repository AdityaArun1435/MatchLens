"""Generate -> validate -> retry once with the errors -> drop invalid parts -> template fallback."""
import hashlib
import json
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from .. import config
from ..llm import LLMError, LLMProvider
from ..service import ProcessedMatch
from . import cache, names_i18n, prompts, rules, translate
from .shootout import HIDDEN_FROM_MODEL, shootout_paragraph
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


def _english_only(language: str) -> None:
    if language != "en":
        raise ValueError("run_recap and run_explanation write English only; get_recap and get_explanation translate it")


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
def _recap_attempt(data, validator: Validator, attempt_no: int, required: list | None = None) -> _Attempt:
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
        errs = validator.check_paragraph(text, p.cites) + rules.check_no_shootout(text, p.cites, validator.match.moments)
        att.items.append((i, text, p.cites, errs))
        errors += [f"Paragraph {i}: {e}" for e in errs]
    for idx, repeats in rules.repeated_sentences([text for _, text, _, _ in att.items]).items():
        number, text, cites, errs = att.items[idx]
        att.items[idx] = (number, text, cites, errs + repeats)
        errors += [f"Paragraph {number}: {e}" for e in repeats]
    if required:
        cited = {c for _, _, cites, errs in att.items if not errs for c in cites}
        if missing := rules.missing_goals(cited, required):
            errors.append(rules.coverage_error(missing))
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
    _english_only(language)
    cutoff = config.RECAP_MIN_IMPORTANCE if min_importance is None else min_importance
    report = ValidationReport(method="llm")
    ctx = build_context(match, min_importance=cutoff, exclude_types=HIDDEN_FROM_MODEL)
    if not ctx.shown_ids:
        ctx = build_context(match, min_importance=0.0, exclude_types=HIDDEN_FROM_MODEL)
        report.notes.append(f"no moment reached importance {cutoff}; every moment was provided instead")
    if not ctx.shown_ids:
        report.method, report.fallback_reason = "fallback", "the match has no detected moments"
        return fallback_recap(match, length, cutoff), report

    validator = Validator(match, ctx, audience, language)
    required = [m for m in ctx.moments.values() if m.type == "goal"]
    lo_hi = config.PARAGRAPHS_PER_LENGTH[length]
    system = prompts.load("system_base")
    user = prompts.render(
        prompts.load("recap_task"),
        context=ctx.text,
        audience=audience,
        audience_instructions=prompts.load(f"audience_{audience}"),
        wording=rules.wording_instructions(audience),
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
        att = _Attempt(failed) if failed else _recap_attempt(data, validator, n, required)
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
    paragraphs = [RecapParagraph(text=t, cites=c) for _, t, c, _ in best.valid]
    if missing := rules.missing_goals({c for p in paragraphs for c in p.cites}, required):
        report.notes.append("not covered after the retry: " + ", ".join(f"{g.id} ({g.clock_label})" for g in missing))
    if (shootout := shootout_paragraph(match, audience)) is not None:
        paragraphs.append(shootout)
        report.notes.append("the shootout paragraph was written from the kick list, not by the model")
        full = Validator(match, build_context(match, min_importance=0.0), audience)
        if problems := full.check_paragraph(shootout.text, shootout.cites):
            report.notes.append("WARNING: the written shootout paragraph failed validation: " + "; ".join(problems))
    return Recap(title=title, paragraphs=paragraphs), report


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
    _english_only(language)
    ctx: Context = build_context(match, min_importance=0.0, target=moment_id)
    report = ValidationReport(method="llm")
    validator = Validator(match, ctx, audience, language)
    system = prompts.load("system_base")
    user = prompts.render(
        prompts.load("explain_task"),
        context=ctx.text,
        moment_id=moment_id,
        audience=audience,
        audience_instructions=prompts.load(f"audience_{audience}"),
        wording=rules.wording_instructions(audience),
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
def _names_key(language: str) -> int:
    """Changes when the language's name map changes, so a hand correction invalidates cached translations."""
    return int(hashlib.sha256(json.dumps(names_i18n.load_map(language).names, sort_keys=True).encode()).hexdigest()[:8], 16)


def _recap_path(match: ProcessedMatch, req: RecapRequest, provider: LLMProvider):
    extra = {} if req.language == "en" else {"names": _names_key(req.language)}
    return cache.cache_file(
        "recap", match.meta.match_id, provider.name,
        audience=req.audience, length=req.length, language=req.language, cutoff=config.RECAP_MIN_IMPORTANCE, **extra,
    )


def peek_recap(match: ProcessedMatch, req: RecapRequest, provider: LLMProvider) -> RecapResult | None:
    """The cached recap for these settings, or None. Never calls the model."""
    hit = cache.read(_recap_path(match, req, provider), RecapResult)
    return hit.model_copy(update={"cached": True}) if hit else None


def peek_explanation(match: ProcessedMatch, moment_id: str, audience: str, language: str, provider: LLMProvider) -> ExplainResult | None:
    hit = cache.read(_explain_path(match, moment_id, audience, language, provider), ExplainResult)
    return hit.model_copy(update={"cached": True}) if hit else None


def get_recap(match: ProcessedMatch, req: RecapRequest, provider: LLMProvider) -> RecapResult:
    if req.language != "en":
        return _get_translated_recap(match, req, provider)
    path = _recap_path(match, req, provider)
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


def _get_translated_recap(match: ProcessedMatch, req: RecapRequest, provider: LLMProvider) -> RecapResult:
    """Validated English first (cached on its own), then paragraph-by-paragraph translation."""
    path = _recap_path(match, req, provider)
    if not req.refresh and (hit := cache.read(path, RecapResult)):
        return hit.model_copy(update={"cached": True})
    english = get_recap(match, req.model_copy(update={"language": "en"}), provider)
    recap, treport = translate.translate_recap(match, english.recap, req.language, req.audience, provider)
    result = RecapResult(
        match_id=match.meta.match_id, audience=req.audience, length=req.length, language=req.language,
        model=provider.name, recap=recap, report=english.report.model_copy(update={"translation": treport}),
        generation_seconds=round(english.generation_seconds + treport.seconds, 2), source_recap=english.recap,
    )
    if english.report.method == "llm" and treport.fallbacks == 0:  # a paragraph left in English is retried next time
        cache.write(_recap_path(match, req, provider), result)  # recomputed: translating may have added names to the map
    return result


def _explain_path(match: ProcessedMatch, moment_id: str, audience: str, language: str, provider: LLMProvider):
    extra = {} if language == "en" else {"names": _names_key(language)}
    return cache.cache_file(
        f"explain-{moment_id}", match.meta.match_id, provider.name, audience=audience, language=language, **extra
    )


def get_explanation(
    match: ProcessedMatch, moment_id: str, audience: str, language: str, provider: LLMProvider, refresh: bool = False
) -> ExplainResult:
    path = _explain_path(match, moment_id, audience, language, provider)
    if not refresh and (hit := cache.read(path, ExplainResult)):
        return hit.model_copy(update={"cached": True})
    start = time.perf_counter()
    if language == "en":
        explanation, report = run_explanation(match, moment_id, audience, language, provider)
        source = None
    else:
        source_result = get_explanation(match, moment_id, audience, "en", provider, refresh)
        explanation, treport = translate.translate_explanation(match, source_result.explanation, language, audience, provider)
        report = source_result.report.model_copy(update={"translation": treport})
        source = source_result.explanation
    result = ExplainResult(
        match_id=match.meta.match_id, moment_id=moment_id, audience=audience, language=language,
        model=provider.name, explanation=explanation, report=report,
        generation_seconds=round(time.perf_counter() - start, 2), source_explanation=source,
    )
    if report.method == "llm" and not (report.translation and report.translation.fallbacks):
        cache.write(_explain_path(match, moment_id, audience, language, provider), result)
    return result
