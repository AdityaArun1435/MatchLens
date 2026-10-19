"""Generate a grounded recap with the local LLM and print it with citations, validation report and timing.

Usage (PowerShell or any shell):
    python scripts/generate_recap.py                              # default match, analyst, medium
    python scripts/generate_recap.py --match 3869685 --audience fan --length short
    python scripts/generate_recap.py --audience all --out recaps.md
    python scripts/generate_recap.py --template                   # deterministic baseline, no LLM
    python scripts/generate_recap.py --explain m_005 --audience broadcaster
    python scripts/generate_recap.py --model gemma3:12b           # override the model for this run
    python scripts/generate_recap.py --language hi --back-translate  # Hindi recap (translated from validated English)
    python scripts/generate_recap.py --audience all --language all --back-translate --out recaps_hi_ta.md
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matchlens import config, loader, service  # noqa: E402
from matchlens.llm import LLMError, LLMUnavailable, OllamaProvider  # noqa: E402
from matchlens.recap import pipeline, translate  # noqa: E402
from matchlens.recap.fallback import fallback_explanation, fallback_recap  # noqa: E402
from matchlens.recap.models import RecapRequest, ValidationReport  # noqa: E402


def render_report(report: ValidationReport) -> list[str]:
    lines = [
        f"validation: method={report.method} attempts={len(report.attempts)} retried={report.retried} "
        f"dropped={len(report.dropped)} title_replaced={report.title_replaced}"
    ]
    if report.fallback_reason:
        lines.append(f"  fallback reason: {report.fallback_reason}")
    for a in report.attempts:
        status = f"{a.items_valid}/{a.items_total} valid" if a.llm_error is None else f"no usable answer: {a.llm_error}"
        lines.append(f"  attempt {a.attempt}: {status}")
        lines += [f"    - {e}" for e in a.errors]
    for d in report.dropped:
        lines.append(f"  dropped paragraph {d.index}: {d.text!r} cites {d.cites}")
    lines += [f"  note: {n}" for n in report.notes]
    if report.translation:
        tr = report.translation
        lines.append(
            f"translation ({tr.language}): units={len(tr.units)} retried={tr.retries} english_fallback={tr.fallbacks} "
            f"names_added={len(tr.names_added)} names_missing={len(tr.names_missing)} translation_time={tr.seconds}s"
        )
        for u in tr.units:
            if u.attempts != 1 or u.status != "translated" or u.notes:
                lines.append(f"  {u.unit}: {u.status} after {u.attempts} attempt(s)")
                lines += [f"    - {e}" for e in u.errors] + [f"    - note: {n}" for n in u.notes]
        if tr.names_missing:
            lines.append(f"  names without a spelling: {', '.join(tr.names_missing)}")
    return lines


def render_recap(recap, header: str, report: ValidationReport, backs: dict[str, str] | None = None) -> list[str]:
    backs = backs or {}
    lines = [header, "", recap.title]
    if "title" in backs:
        lines.append(f"  (back-translated: {backs['title']})")
    lines.append("")
    for i, p in enumerate(recap.paragraphs, start=1):
        lines.append(f"{p.text} [{', '.join(p.cites)}]")
        if p.note:
            lines.append(f"  NOTE: {p.note}")
        if f"paragraph {i}" in backs:
            lines.append(f"  (back-translated: {backs[f'paragraph {i}']})")
        lines.append("")
    return lines + render_report(report) + [""]


def back_translations(res, provider) -> dict[str, str]:
    """English back-translation of every translated unit, for a human to judge meaning drift."""
    lang = res.language
    out = {"title": translate.back_translate(res.recap.title, lang, provider)}
    for i, p in enumerate(res.recap.paragraphs, start=1):
        if p.language == lang:
            out[f"paragraph {i}"] = translate.back_translate(p.text, lang, provider)
    return out


def one(match, args, provider, audience: str, language: str) -> list[str]:
    if args.explain:
        res = pipeline.get_explanation(match, args.explain, audience, language, provider, args.refresh)
        ex = res.explanation
        lines = [
            f"=== explain {args.explain} / {audience} / {language} | {res.model} | {res.generation_seconds}s"
            f"{' (cached)' if res.cached else ''} ===", "",
            f"Why it mattered: {ex.why_it_mattered}", f"Context: {ex.context}", f"[{', '.join(ex.cites)}]",
        ]
        lines += [f"  NOTE: {n}" for n in ex.notes]
        return lines + [""] + render_report(res.report) + [""]
    req = RecapRequest(audience=audience, length=args.length, language=language, refresh=args.refresh)
    res = pipeline.get_recap(match, req, provider)
    header = (
        f"=== {audience} / {args.length} / {language} | {res.model} | {res.generation_seconds}s"
        f"{' (cached)' if res.cached else ''} ==="
    )
    backs = back_translations(res, provider) if args.back_translate and language != "en" else None
    return render_recap(res.recap, header, res.report, backs)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # PowerShell code pages choke on accents
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--match", type=int, help="match id; defaults to the 2022 World Cup final")
    p.add_argument("--audience", default="analyst", choices=[*config.AUDIENCES, "all"])
    p.add_argument("--length", default="medium", choices=config.LENGTHS)
    p.add_argument("--language", default="en", choices=[*config.LANGUAGES, "all"])
    p.add_argument("--back-translate", action="store_true", help="also translate each hi/ta recap back to English (not used for validation)")
    p.add_argument("--explain", metavar="MOMENT_ID", help="explain one moment instead of writing a recap")
    p.add_argument("--template", action="store_true", help="print the deterministic template recap (no LLM)")
    p.add_argument("--refresh", action="store_true", help="ignore the cache")
    p.add_argument("--model", help=f"Ollama model (default {config.OLLAMA_MODEL}, env MATCHLENS_OLLAMA_MODEL)")
    p.add_argument("--out", help="also write the output to this Markdown file")
    args = p.parse_args()

    match_id = args.match or loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"]
    match = service.get_match(match_id)
    out: list[str] = [f"{match.meta.home_team} v {match.meta.away_team} ({match.meta.stage}, {match.meta.date}), match {match_id}", ""]

    if args.template:
        recap = fallback_recap(match, args.length)
        out += render_recap(recap, f"=== template baseline / {args.length} (no LLM) ===", ValidationReport(method="fallback"))
    else:
        provider = OllamaProvider(model=args.model)
        audiences = list(config.AUDIENCES) if args.audience == "all" else [args.audience]
        languages = list(config.LANGUAGES) if args.language == "all" else [args.language]
        started = time.perf_counter()
        try:
            for audience in audiences:
                for language in languages:
                    out += one(match, args, provider, audience, language)
        except LLMUnavailable as exc:
            print(f"Ollama is not available: {exc}", file=sys.stderr)
            sys.exit(2)
        except LLMError as exc:
            print(f"LLM error: {exc}", file=sys.stderr)
            sys.exit(3)
        out.append(f"total time: {time.perf_counter() - started:.1f}s")

    text = "\n".join(out)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
