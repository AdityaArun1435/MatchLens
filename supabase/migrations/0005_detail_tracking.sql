-- Track, per fixture, whether its events and lineups were fetched. A finished match is fetched once and never again.
--   null         not fetched yet (pending)
--   'ok'         events and/or lineups stored
--   'empty'      the source answered but has no events or lineups for it
--   'unavailable' we could not link it to an API-Football fixture after several tries
alter table fixtures
  add column detail_status text check (detail_status in ('ok', 'empty', 'unavailable')),
  add column detail_fetched_at timestamptz,
  add column map_attempts integer not null default 0;

-- The backfill reads the oldest unfinished-detail matches first.
create index fixtures_backfill_idx on fixtures (utc_date) where detail_status is null and status = 'FINISHED';
