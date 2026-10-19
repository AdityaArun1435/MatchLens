# StatsBomb data notes

Written from inspecting the real JSON (open-data `master`, data version 1.1.0) for
three matches: 3869685 (2022 final), 7580 (2018 R16), 3869321 (2022 QF). Own goals and
straight reds do not occur in those three, so their shape was checked against 2018
World Cup matches 8650 (Brazil v Belgium, own goal) and 7586 (Sweden v Switzerland, red card).

## Files
| Path under `data/` | Content |
|---|---|
| `competitions.json` | one row per competition and season (`competition_id`, `season_id`) |
| `matches/{competition_id}/{season_id}.json` | one row per match: `match_id`, `home_team.home_team_name`, `away_team.away_team_name`, `home_score`, `away_score`, `competition_stage.name`, `match_date` |
| `events/{match_id}.json` | flat list of events, ordered by `index` |
| `lineups/{match_id}.json` | two entries (`team_id`, `team_name`, `lineup[]` with `player_id`, `player_name`, `jersey_number`, `cards[]`, `positions[]`) |

`home_score` / `away_score` in the matches file are the score after extra time and
**exclude** the shootout (final: 3-3, not 3-3 plus pens).

## Fields used on every event
`id` (uuid), `index` (1-based, strictly increasing, the reliable ordering key), `period`,
`timestamp` (`HH:MM:SS.mmm`), `minute`, `second`, `type.name`, `team.{id,name}`,
`player.{id,name}` (absent on non-player events), `location` ([x,y] on a 120x80 pitch, may be absent),
`possession` (int), `possession_team`, `related_events` (list of uuids, may be absent).

## Periods and clocks
* `period`: 1, 2 regular time; 3, 4 extra time; **5 = penalty shootout**.
* `timestamp` restarts at `00:00:00` in every period. `minute` / `second` do **not**: they are
  period offset plus timestamp. Offsets seen: p1 0, p2 45:00, p3 90:00, p4 105:00. The shootout
  (p5) reports `minute` 120 onwards, with its own timestamp starting at 0.
* Stoppage time is not separate. Period 1 of the final runs to 52:34 and period 2 to 98:37,
  so `minute` is 45..52 inside period 1 and 90..98 inside period 2. In the QF period 2 reaches 100+.
  Consequence: **`minute` is not unique across periods** (minute 45 exists in p1 stoppage and at the start of p2).
  `match_clock_seconds` is therefore the broadcast clock (`offset + timestamp`) and is not monotonic across a
  period boundary; use `index` for ordering and `(period, minute)` for bucketing.
* `minute` is the elapsed whole minute (22:24 elapsed is `minute` 22). Football reporting says 23'. The
  display label uses `floor(elapsed) + 1`, and shows `45+N'` / `90+N'` / `105+N'` / `120+N'` once past a period's nominal end.
* `Half Start` and `Half End` appear twice per period (one per team).

## Shots
`type.name == "Shot"`. Under `shot`:
* `statsbomb_xg` (float). Present on all 90 shots checked; code still tolerates missing.
* `outcome.name`: `Goal`, `Saved`, `Blocked`, `Off T`, `Wayward`, `Post` (also `Saved Off Target`, `Saved to Post` exist in the spec).
* `type.name`: `Open Play`, `Penalty`, `Free Kick`, `Corner`, `Kick Off`.
* `key_pass_id` (uuid of the assisting pass), `freeze_frame`, `end_location`.

**Difference from the brief's assumption:** shootout kicks (period 5) are ordinary `Shot` events with
`type = Penalty` **and a `statsbomb_xg` of 0.7835**. They must be excluded from xG, shot counts and the in-play
score by filtering on `period == 5`, not on shot type (in-play penalties are real shots with the same xG).

## Goals and score
* A scored shot is `shot.outcome.name == "Goal"`, credited to `team`.
* Own goals are **not shots**. Two events share a timestamp: `Own Goal Against` (`team` = the side of the
  player who put it in, has `player`) and `Own Goal For` (`team` = the side credited, no `player`, no `location`).
  They link through `related_events`. The goal counts for the `Own Goal For` team.
* No separate "goal" event exists. Score is derived by walking events in `index` order.

## Passes and build-up
`type.name == "Pass"`: `pass.recipient`, `pass.outcome` (**absent when the pass was completed**; otherwise
`Incomplete`, `Out`, `Pass Offside`, `Unknown`), `pass.goal_assist`, `pass.shot_assist`.
`possession` groups a team's sequence. A possession also contains opposition events (duels, keeper actions),
so build-up must filter on `team`. The scoring shot belongs to the same `possession` as the pass chain before it.

## Substitutions
`type.name == "Substitution"`: `team` = side making the change, `player` = player **going off**,
`substitution.replacement` = player coming on, `substitution.outcome.name` = `Tactical` or `Injury`.
A sub at a period boundary is stamped at timestamp `00:00:00` of the new period (Molina, 90:00).
Double substitutions are separate events seconds apart.

## Cards
No card event type. Cards live inside two event types:
* `Foul Committed` -> `foul_committed.card.name`
* `Bad Behaviour` -> `bad_behaviour.card.name`

Values seen: `Yellow Card`, `Second Yellow`, `Red Card`. The card is attached to the offending `team`/`player`.
`Second Yellow` is its own record, and the first yellow is a separate earlier event. None of the three
matches has a straight red. The QF has a `Second Yellow` (Dumfries) in **period 5**, after the last kick.

## Other
* `Player Off` / `Player On` are bookkeeping events, ignored.
* `Starting XI` events carry `tactics.lineup`.
* Lineups: `player_nickname` is the short name (null for some players). Mostly usable ("Lionel Messi"), but not always:
  Kolo Muani is "Randal Kolo" and Mac Allister is "Alexis MacAllister". `config.DISPLAY_NAME_OVERRIDES` corrects these.
* No possession-share field exists. It is derived in `summary.py` from the `possession` sequence numbers (time from the first event of one possession to the first event of the next, same period, credited to `possession_team`).
