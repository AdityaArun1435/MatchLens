# MatchLens (Phase 1: data layer)

Local-only football match intelligence. Phase 1 loads StatsBomb open data, normalises the events, detects
the key moments of a match with plain Python, and serves everything through a small FastAPI app. No LLM,
no ML, no paid APIs, no keys.

Default match: **2022 FIFA World Cup final, Argentina v France** (3-3 after extra time, Argentina won 4-2 on penalties).
Two more are preloaded: **France 4-3 Argentina** (2018 round of 16, seven goals) and **Netherlands 2-2 Argentina**
(2022 quarter-final, 90+11' equaliser, extra time, shootout, 16 card events). Match ids are resolved from StatsBomb's
`matches.json` by team and stage, never hard-coded.

## Setup (Windows 11, PowerShell, Python 3.11+)

```powershell
git clone <this repo>; cd MatchLens
py -3.11 -m venv .venv            # or: python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python scripts/fetch_data.py      # one-off download into data/raw/ (about 11 MB), then everything runs offline
```

`data/raw/` is not in git. StatsBomb's data agreement (`LICENSE.pdf` in their repo, clause 1.2.1) forbids
distributing or reproducing the data to third parties, so each user fetches it themselves. Tests that need the data
are skipped (not failed) until you have run `fetch_data.py`.

Add any other match: `python scripts/fetch_data.py --add MATCH_ID:COMPETITION_ID:SEASON_ID`.

## Run

```powershell
python scripts/inspect_match.py                      # moments table for the final
python scripts/inspect_match.py --all --stats        # all preloaded matches, with each moment's numbers
python scripts/inspect_match.py --match-id 7580 --min-importance 0.5

uvicorn matchlens.api:app --reload                   # http://127.0.0.1:8000/docs
python -m pytest                                     # all offline
```

### API

| Endpoint | Returns |
|---|---|
| `GET /matches` | preloaded matches: metadata, extra time flag, shootout winner, moment count |
| `GET /matches/{id}/summary` | `MatchSummary`: scores (90 min, extra time, final), shootout, xG, shots, possession, per-minute xG timeline |
| `GET /matches/{id}/moments?min_importance=` | moments in match order |
| `GET /matches/{id}/events?from_minute=&to_minute=&period=` | normalised events in match order (for live replay) |

Each match is loaded and processed once and kept in memory. `minute` is the StatsBomb elapsed minute and repeats
across a period boundary (stoppage time of the first half overlaps the start of the second), so pass `period`
when you need to be exact. Order by `index`, not by minute.

## Layout

```
matchlens/config.py        every threshold and default
matchlens/loader.py        download + cache of raw JSON in data/raw
matchlens/normalise.py     raw event -> Event (clock labels, shootout handling)
matchlens/importance.py    importance scoring, one place to tune
matchlens/detect/          one module per moment type, MatchContext holds the goal log
matchlens/summary.py       MatchSummary
matchlens/service.py       per-match cache used by the API and scripts
docs/data_notes.md         the real StatsBomb fields this code relies on
```

## Moment definitions

Every moment has an `id` (`m_001`, in match order), `minute`, `clock_label` (`23'`, `45+2'`, `90+3'`, `Pens`),
`period`, `type`, `team`, `players`, `score_before` / `score_after` (home, away; in-play goals only),
`importance` (0 to 1), a one-line `headline`, the `stats` behind it and `evidence` (event ids, all present in
`/events`). Headlines state numbers and never claim a cause.

* **goal**: any in-play goal, including penalties and own goals (credited to the team that benefits). Stats hold
  the goal kind, assist, xG, whether it took the lead or equalised, any earlier shot in the same possession (rebounds)
  and the completed passes of the scoring team in that possession before the shot.
* **big_chance_missed**: an in-play shot with xG at or above `BIG_CHANCE_XG` (0.3) that did not score.
* **red_card** / **second_yellow**: straight reds and second yellows. Plain yellows are not moments.
* **momentum_swing**: every minute, compare the two teams' xG over the previous 10 minutes. The window leader is the
  team ahead by at least `MOMENTUM_MIN_LEAD_XG` (0.15); otherwise nobody leads. A swing is logged when a different team
  becomes leader and stays leader for at least `MOMENTUM_HOLD_MIN` (5) minutes. Windows are cut at the start of each
  period and state is reset, so nothing spans half-time or the break before extra time. Both teams' xG and shots are in `stats`.
* **substitution_impact**: for a team's substitution (same-team changes within 2 minutes count as one), compare that
  team's xG and shots in the window before and after, inside the same period. Flagged when xG moves by at least 0.4 or
  shots by at least 3 per 10 minutes, up or down. Windows shrink to fit the period; changes without 5 minutes on both
  sides in the period are skipped. Opponent numbers are included for context.
* **penalty_shootout**: one moment with every kick in order, the tally and the winner.

Penalties awarded in play are excluded from the momentum and substitution windows (`EXCLUDE_PENALTIES_FROM_WINDOWS`),
because a 0.78 xG penalty reflects a referee decision rather than a spell of play. They still count as goals and
in all match totals. Shootout kicks never count towards score, xG or shot totals.

### Importance

`matchlens/importance.py` documents and holds all weights. In short: goals 0.60, +0.30 if the goal takes the lead or
equalises, +0.10 if late or in extra time; big chances 0.25 + 0.5 x xG (+0.10 when the score is within a goal); red
card 0.70, second yellow 0.65; shootout 0.95; momentum swings 0.25 to 0.55 by xG lead; substitutions 0.15 to 0.40 by xG change.

## Attribution

Data: **StatsBomb Open Data**, https://github.com/statsbomb/open-data. Used under the StatsBomb Public Data User
Agreement. If you publish or share analysis built on this data, state StatsBomb as the source and use their logo
(see their media pack: https://statsbomb.com/media-pack/). StatsBomb provides the data as is, and this project is
not affiliated with or endorsed by StatsBomb.
