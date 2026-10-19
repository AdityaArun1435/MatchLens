"""Generate a grounded recap with the local LLM and print it with citations, validation report and timing.

Usage (PowerShell or any shell):
    python scripts/generate_recap.py                              # default match, analyst, medium
    python scripts/generate_recap.py --match 3869685 --audience fan --length short
    python scripts/generate_recap.py --audience all --out recaps.md
    python scripts/generate_recap.py --template                   # deterministic baseline, no LLM
    python scripts/generate_recap.py --explain m_005 --audience broadcaster
    python scripts/generate_recap.py --model gemma3:12b           # override the model for this run
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matchlens import config, loader, service  # noqa: E402
from matchlens.llm import LLMError, LLMUnavailable, OllamaProvider  # noqa: E402
from matchlens.recap import pipeline  # noqa: E402
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
    return lines


def render_recap(recap, header: str, report: ValidationReport) -> list[str]:
    lines = [header, "", recap.title, ""]
    for p in recap.paragraphs:
        lines += [f"{p.text} [{', '.join(p.cites)}]", ""]
    return lines + render_report(report) + [""]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # PowerShell code pages choke on accents
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--match", type=int, help="match id; defaults to the 2022 World Cup final")
    p.add_argument("--audience", default="analyst", choices=[*config.AUDIENCES, "all"])
    p.add_argument("--length", default="medium", choices=config.LENGTHS)
    p.add_argument("--language", default="en", choices=config.LANGUAGES)
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
        started = time.perf_counter()
        try:
            for audience in audiences:
                if args.explain:
                    res = pipeline.get_explanation(match, args.explain, audience, args.language, provider, args.refresh)
                    ex = res.explanation
                    out += [
                        f"=== explain {args.explain} / {audience} / {args.language} | {res.model} | {res.generation_seconds}s"
                        f"{' (cached)' if res.cached else ''} ===", "",
                        f"Why it mattered: {ex.why_it_mattered}", f"Context: {ex.context}", f"[{', '.join(ex.cites)}]", "",
                        *render_report(res.report), "",
                    ]
                else:
                    res = pipeline.get_recap(match, RecapRequest(audience=audience, length=args.length, language=args.language, refresh=args.refresh), provider)
                    header = (
                        f"=== {audience} / {args.length} / {args.language} | {res.model} | {res.generation_seconds}s"
                        f"{' (cached)' if res.cached else ''} ==="
                    )
                    out += render_recap(res.recap, header, res.report)
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
