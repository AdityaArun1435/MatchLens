# Data sources for the live site

Checked on 2026-10-20. Free tiers change without notice, so the code reads limits from config and tracks usage itself.

## football-data.org (free plan)

Verified on the official [pricing page](https://www.football-data.org/pricing) and [request-throttling docs](https://docs.football-data.org/general/v4/policies.html).

| Item | Free plan |
|---|---|
| Rate limit | 10 requests per minute with a token (`X-Auth-Token`). No stated daily cap. Unauthenticated: 100 per day, competition list only. |
| Competitions | 12 (the top European leagues, Champions League, European Championship, World Cup, Eredivisie, Primeira Liga, Championship, Brasileirao) |
| Included | Fixtures, results, league tables |
| Scores | **Delayed** (not real time) |
| Not included | Lineups and substitutions, goal scorers, bookings (paid "Deep Data", EUR 29/month), odds (paid add-on, EUR 15/month) |
| Attribution / caching / redistribution | **Not stated** on the pricing or policy pages. The site points questions to the owner by email. |

Use: the backbone for competitions, teams, fixtures, standings. Reliable and generous on rate.

## API-Football (api-sports.io, free plan)

The official pricing and docs pages sit behind a bot check and could not be fetched, so these numbers come from secondary sources and the [terms summary](https://api-sports.io/terms). **Confirm all of it in your dashboard when you add the key** (the code logs the real quota from response headers).

| Item | Free plan (as reported) |
|---|---|
| Quota | 100 requests per day, resets 00:00 UTC, no rollover |
| Rate limit | 10 per minute |
| Endpoints | All of them, including live, events, lineups, statistics, odds |
| Seasons | Reports conflict. Some say the current season is limited on free. **Unverified: test with the key first.** |
| Terms | No licence to publish league-owned data is granted ("rights come from the relevant authorities"); no reselling raw data; no multiple accounts to dodge limits. Caching and attribution are not addressed. |

Use: live scores, events, lineups, team and player statistics, odds. One `fixtures?live=all` call returns every live match with its events, so it is the cheapest live feed.

## Recommendation

| Feature | Source | Why |
|---|---|---|
| Competitions, teams, fixtures, results | football-data.org | Cheap, 10 per minute, no daily cap |
| Standings | football-data.org | One call per competition |
| Live score and events | API-Football `fixtures?live=all` | Real-time, events included in one call |
| Lineups, match statistics | API-Football `fixtures?id=` | One call returns events, lineups and statistics; cached |
| Odds (L2+) | API-Football `odds` | football-data.org odds are paid |
| Top scorers (L2+) | football-data.org `/scorers` | Free |

## Request budget (per day)

Visitors never call a source. Only the scheduled refresh does, so usage depends on the clock.

**API-Football, 100 per day (hard guard at 95 in code):**

| Use | Calls/day | Rule |
|---|---|---|
| Live poll (`live=all`) | up to 70 | Only while a match is in its live window; at most one every 4 minutes, so about 4.7 hours of continuous live coverage; the interval stretches automatically when the day's budget runs low |
| Day mapping (`fixtures?date=`) | 2 | Links our fixture ids to API-Football ids; also refreshes scores |
| Match detail (`fixtures?id=`) | up to 20 | Lineups, events, statistics for a match page; cached 2 minutes while live, 6 hours after full time, one per fixture at a time |
| Reserve | 5 | Never spent |

**football-data.org, 10 per minute (we cap ourselves at 4 per minute, about 5,700 per day):**

| Use | Rule |
|---|---|
| Fixtures per tracked competition | One competition per minute in rotation, window of -2 to +10 days |
| Standings | One competition per tick, each at most every 30 minutes (every 5 while a match of that competition is live) |

The free-plan score delay means football-data.org scores are a fallback; live state from API-Football wins when present.

## Terms and attribution: open questions

- Neither provider states caching or redistribution rules on the free plan. The site caches in Supabase (a short TTL for live data) and shows "Data: football-data.org and API-Football" in the footer.
- Because API-Football says it grants no licence to publish league-owned data, treat this as a **personal and portfolio project**. Do not put ads, paywalls or betting links on it. Before any commercial use, get written confirmation from both providers.
- Emailing football-data.org about public display on the free plan is the cheapest way to get a real answer.
