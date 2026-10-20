# Why finished matches had no events or lineups, and the options

Checked 2026-10-20 with real calls, using Brighton 5-0 Crystal Palace (Premier League matchday 7, 18 Oct).

## Cause

The data exists. The site could not link the match to API-Football, because the free plan will not list it.

| Question | Answer (observed) |
|---|---|
| Does football-data.org free return goals, bookings, lineups for this match? | **No.** `GET /v4/matches/560609` returns the score only. The `goals`, `bookings`, `substitutions` and lineup fields are absent. Those are the paid "Deep Data" plan. |
| Does API-Football free allow the current season? | **Not for listing.** `fixtures?league=39&season=2026&...` returns `Free plans do not have access to this season, try from 2022 to 2024.` |
| Can it list matches by date? | **Only yesterday to tomorrow.** `fixtures?date=2026-10-18` returns `Free plans do not have access to this date, try from 2026-10-19 to 2026-10-21.` Also refused: `last=`, `ids=`. |
| Does it return this match's events and lineups? | **Yes, by fixture id.** `fixtures?id=1557429` returns the match with 18 events, both lineups and statistics. Lookup by id works for any season on the free plan. |
| Is there a way to find the id? | **Yes: head-to-head.** `fixtures/headtohead?h2h=51-52` (Brighton, Crystal Palace) lists their fixtures including `1557429`. |

The first version of the refresh mapped fixtures by listing `fixtures?date=<today>` and matching names. That only ever sees today (the free window), and the site only started running on 20 Oct, so every match played before then had no API-Football id and was never fetched. Name matching itself was fine: "Brighton & Hove Albion FC" normalises to "brighton hove albion", which contains "brighton".

## What was fixed

- Old matches are linked through head-to-head: resolve both team ids (league team list from season 2024, then a name search for promoted clubs), call head-to-head, pick the fixture in the same league within 12 hours of kick-off. Ids are stored on the fixture and team rows.
- Finished matches are fetched once by id and marked `ok`, `empty` (source has nothing) or `unavailable` (could not be linked after two tries) in `fixtures.detail_status`. They are never fetched again.
- A backfill walks finished matches oldest first. It runs only when nothing is live and the day is under 60 of 95 requests, with its own cap of 45 requests per day. Progress is stored on the fixture rows, so it resumes after any restart. A match the source refuses cannot block the queue.
- football-data.org supplies the full list of finished matches of the season (one request per competition), because the schedule feed only held a 10-day window.
- Empty states are by match status (see `emptyMessage` in `web/components/live/MatchLive.tsx`).

Cost per old match: 2 requests (head-to-head, then lookup), plus a one-off 20 to 40 requests for team ids. At 45 backfill requests per day that is about 20 matches per day, so a season with several hundred finished matches takes a few weeks on the free plan. Matches inside the yesterday-to-tomorrow window cost 1 request.

## Options if that is too slow

Prices come from secondary sources and change; confirm on each pricing page.

| Option | Cost | What it gives |
|---|---|---|
| Stay on API-Football free | $0 | Everything above, slowly. Live data also limited to about 4 minute polling. |
| API-Football Pro | about $19 per month (7,500 requests per day) | Backfill of a whole season in a day, polling every minute, all seasons. |
| football-data.org "Deep Data" | EUR 29 per month | Goals, bookings, substitutions, lineups for the 12 competitions in one list call. No live events stream. |
| Sportmonks Starter | about EUR 29 per month (5 leagues) | Lineups and events, higher limits. Free tier covers only two small leagues. |

Recommendation: keep the free plan for now (it works, only slowly). If you want full history within days and one-minute live updates, API-Football Pro at about $19 is the cheapest real option and needs no code change beyond raising the limits in `matchlens/live/config.py`.
