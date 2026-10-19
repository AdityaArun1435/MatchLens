"""Print a match's moments as a table so they can be checked against what really happened.

Usage (PowerShell or any shell):
    python scripts/inspect_match.py                       # default match (2022 World Cup final)
    python scripts/inspect_match.py --match-id 7580
    python scripts/inspect_match.py --all                 # every preloaded match
    python scripts/inspect_match.py --min-importance 0.5 --stats
"""
import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matchlens import config, loader, service  # noqa: E402

HEADLINE_WIDTH = 92


def print_match(match_id: int, min_importance: float, show_stats: bool, allow_network: bool) -> None:
    m = service.get_match(match_id, allow_network)
    s = m.summary
    home, away = m.meta.home_team, m.meta.away_team
    print(f"\n{home} v {away}  |  {m.meta.competition} {m.meta.season}, {m.meta.stage}, {m.meta.date}  |  match_id {match_id}")
    line = f"Score {s.final_score[0]}-{s.final_score[1]} (after 90: {s.score_after_90[0]}-{s.score_after_90[1]})"
    if s.shootout:
        line += f", shootout {s.shootout['score'][home]}-{s.shootout['score'][away]} won by {s.shootout['winner']}"
    print(line)
    print(
        f"xG {home} {s.total_xg[home]:.2f} - {s.total_xg[away]:.2f} {away} | shots {s.shots[home]}-{s.shots[away]} "
        f"| possession {s.possession_share[home]:.0%}-{s.possession_share[away]:.0%}"
    )
    rows = [x for x in m.moments if x.importance >= min_importance]
    print(f"{len(rows)} of {len(m.moments)} moments (min importance {min_importance})\n")
    print(f"{'id':<6}{'time':<8}{'type':<20}{'team':<13}{'imp':<6}headline")
    print("-" * 140)
    for x in rows:
        wrapped = textwrap.wrap(x.headline, HEADLINE_WIDTH) or [""]
        print(f"{x.id:<6}{x.clock_label:<8}{x.type:<20}{(x.team or '-'):<13}{x.importance:<6.2f}{wrapped[0]}")
        for extra in wrapped[1:]:
            print(f"{'':<53}{extra}")
        if show_stats:
            print(textwrap.indent(json.dumps(x.stats, ensure_ascii=False, default=str), " " * 53))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # PowerShell code pages choke on accents
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--match-id", type=int, help="defaults to the 2022 World Cup final, resolved from the data")
    p.add_argument("--all", action="store_true", help="show every preloaded match")
    p.add_argument("--min-importance", type=float, default=0.0)
    p.add_argument("--stats", action="store_true", help="also print each moment's stats dict")
    p.add_argument("--online", action="store_true", help="allow downloading a match that is not cached")
    args = p.parse_args()
    if args.all:
        ids = [e["match_id"] for e in loader.load_index()]
    else:
        ids = [args.match_id or loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=not args.online)["match_id"]]
    for match_id in ids:
        print_match(match_id, args.min_importance, args.stats, args.online)


if __name__ == "__main__":
    main()
