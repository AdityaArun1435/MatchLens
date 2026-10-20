# Live site: architecture and operations

```
football-data.org ─┐                          ┌─> Next.js pages (/, /fixtures, /standings, /matches)
                   ├─> Python refresh tick ─> Supabase ─> Next.js read API (/api/matches, ...)  ─> browser polls every 30-60 s
API-Football ──────┘   (api/refresh.py)       (tables + api_cache)
        ^
        └── pg_cron + pg_net call /api/refresh every minute
```

Visitors only ever read from Supabase through our own API. Source API usage depends on the clock and the cache TTLs, never on traffic. Limits and the daily budget: [data_sources.md](data_sources.md).

## Pieces

| Piece | Where |
|---|---|
| Source clients, cache, budget, retries | `matchlens/live/` (`footballdata.py`, `apifootball.py`, `base.py`) |
| One refresh tick | `matchlens/live/refresh.py` |
| Vercel Python function | `web/api/refresh.py` (copies of `matchlens/` are bundled by `web/scripts/sync-python.mjs`) |
| Schema and cron | `supabase/migrations/` |
| Pages and read API | `web/app/(live)/`, `web/app/api/`, `web/lib/live/` |
| Classic StatsBomb matches | `web/app/classic/` (needs the local FastAPI backend) |

## Scheduler choice: Supabase pg_cron

Vercel cron on the Hobby plan runs at most once a day, too slow for live scores. Supabase `pg_cron` runs every minute on the free plan, and `pg_net` posts to `/api/refresh` with `Authorization: Bearer <CRON_SECRET>`. The URL and secret sit in Supabase Vault (migration `0004`). The function returns `401` without the secret.

Each tick does a little work and skips the rest:

- one football-data.org competition's fixtures (rotation), one standings table every third minute (both cached, so repeats cost nothing);
- map today's fixtures to API-Football ids (cached 3 hours);
- one `live=all` call, only while a tracked match is in its live window and the interval since the last poll has passed (4 minutes, stretching as the daily budget is used);
- lineups and events for matches about to start or just finished, a few per tick, retried at most every 10 minutes.

If a source fails, the stale cached copy is used. If a budget is used up, that step is skipped and reported in the tick response.

## Setup from scratch

1. Create a Supabase project and apply `supabase/migrations/*.sql` in order.
2. Create a Vercel project with root directory `web`. Set the variables from `.env.example`.
3. After the first deploy, tell Supabase where to call:
   ```sql
   select vault.create_secret('https://<your-site>/api/refresh', 'refresh_url');
   select vault.create_secret('<CRON_SECRET>', 'refresh_secret');
   ```
4. Check the result of a run: `python scripts/run_refresh.py` locally (reads `.env.local`), or look at the function logs on Vercel.

## Known limits

- Live data is as fresh as the polling interval (about 4 minutes on the free API-Football plan), not second by second. The page says when it last checked.
- `/classic` works only where the FastAPI backend runs. On the deployed site it shows the offline message.
- Hindi, Tamil, audience modes and Ollama are still in the repo and in the classic pages. Removing them from the web build is a later phase.
