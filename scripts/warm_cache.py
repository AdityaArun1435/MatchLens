"""Pre-generate every recap and explanation so the web app can show them instantly.

    python scripts/warm_cache.py                      # 3 matches x 3 audiences x 2 lengths x en/hi/ta, plus explanations
    python scripts/warm_cache.py --no-explain         # recaps only
    python scripts/warm_cache.py --languages en       # only English
    python scripts/warm_cache.py --match 3869685 --min-importance 0.7 --max-minutes 40   # one match, big moments, time-boxed

Resumable: anything already in the cache (data/generated/) is skipped, so stop it with Ctrl+C and run it again to carry on.
A result that fell back to the template, or has a paragraph left in English, is not cached by design and is tried again
the next time the script runs. Explanations are made for every moment with importance >= --min-importance, in every
audience and language that was asked for. Needs Ollama running with the configured model.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matchlens import config, loader, service  # noqa: E402
from matchlens.llm import LLMError, LLMUnavailable, OllamaProvider  # noqa: E402
from matchlens.recap import pipeline  # noqa: E402
from matchlens.recap.models import RecapRequest  # noqa: E402


def fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--matches", "--match", type=int, nargs="*", help="match ids (default: every preloaded match)")
    p.add_argument("--audiences", nargs="*", default=list(config.AUDIENCES), choices=config.AUDIENCES)
    p.add_argument("--lengths", nargs="*", default=list(config.LENGTHS), choices=config.LENGTHS)
    p.add_argument("--languages", nargs="*", default=list(config.LANGUAGES), choices=config.LANGUAGES)
    p.add_argument("--no-explain", action="store_true")
    p.add_argument("--min-importance", type=float, default=0.5)
    p.add_argument("--max-minutes", type=float, help="stop after this many minutes, even if jobs are left (resume later)")
    p.add_argument("--model")
    args = p.parse_args()

    ids = args.matches or [e["match_id"] for e in loader.load_index()]
    matches = [service.get_match(i) for i in ids]
    provider = OllamaProvider(model=args.model)

    jobs: list[tuple[str, object]] = []
    for m in matches:
        for audience in args.audiences:
            for length in args.lengths:
                for language in args.languages:  # English first: the translations reuse it from the cache
                    jobs.append((f"{m.meta.match_id} recap {audience}/{length}/{language}", (m, RecapRequest(audience=audience, length=length, language=language))))
    if not args.no_explain:
        for m in matches:
            for moment in m.moments:
                if moment.importance < args.min_importance:
                    continue
                for audience in args.audiences:
                    for language in args.languages:
                        jobs.append((f"{m.meta.match_id} explain {moment.id} {audience}/{language}", (m, moment.id, audience, language)))

    started = time.perf_counter()
    done = generated = cached = uncached = 0
    print(f"{len(jobs)} jobs with {provider.name}. Skips what is already cached; Ctrl+C to stop, run again to resume.")
    try:
        for n, (label, job) in enumerate(jobs, start=1):
            t0 = time.perf_counter()
            if args.max_minutes and t0 - started > args.max_minutes * 60:
                print(f"\nTime limit of {args.max_minutes:g} minutes reached. Run the script again to resume.")
                break
            if len(job) == 2:
                m, req = job
                result = pipeline.get_recap(m, req, provider)
                problems = result.report.method == "fallback" or bool(result.report.translation and result.report.translation.fallbacks)
            else:
                m, moment_id, audience, language = job
                result = pipeline.get_explanation(m, moment_id, audience, language, provider)
                problems = result.report.method == "fallback" or bool(result.report.translation and result.report.translation.fallbacks)
            took = time.perf_counter() - t0
            done += 1
            if result.cached:
                cached += 1
                status = "cached"
            elif problems:
                uncached += 1
                status = "NOT cached (template or English fallback; will be retried next run)"
            else:
                generated += 1
                status = f"generated in {took:.0f}s"
            elapsed = time.perf_counter() - started
            left = (len(jobs) - n) * (elapsed / n)
            print(f"[{n}/{len(jobs)}] {label}: {status} | elapsed {fmt(elapsed)}, about {fmt(left)} left", flush=True)
    except KeyboardInterrupt:
        print("\nStopped. Run the script again to resume.")
    except LLMUnavailable as exc:
        print(f"\nOllama is not available: {exc}", file=sys.stderr)
        sys.exit(2)
    except LLMError as exc:
        print(f"\nLLM error: {exc}", file=sys.stderr)
        sys.exit(3)

    size = sum(f.stat().st_size for f in config.GENERATED_DIR.rglob("*.json")) if config.GENERATED_DIR.exists() else 0
    print(f"\nDone: {done} jobs, {generated} generated, {cached} already cached, {uncached} not cacheable. Total time {fmt(time.perf_counter() - started)}.")
    print(f"Cache: {config.GENERATED_DIR} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
