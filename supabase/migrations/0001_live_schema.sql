-- MatchLens live site, schema v1.
-- Ids: competitions, teams and fixtures use football-data.org ids. API-Football ids are stored beside them.

create table competitions (
  id integer primary key,
  code text not null unique,
  name text not null,
  area text,
  emblem text,
  af_league_id integer,
  season integer,
  current_matchday integer,
  updated_at timestamptz not null default now()
);

create table teams (
  id integer primary key,
  name text not null,
  short_name text,
  tla text,
  crest text,
  af_team_id integer,
  updated_at timestamptz not null default now()
);

create table fixtures (
  id integer primary key,
  competition_id integer not null references competitions(id),
  season integer,
  matchday integer,
  stage text,
  utc_date timestamptz not null,
  status text not null,            -- football-data.org status: SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED, POSTPONED, ...
  home_team_id integer references teams(id),
  away_team_id integer references teams(id),
  home_score integer,
  away_score integer,
  ht_home_score integer,
  ht_away_score integer,
  winner text,                     -- HOME_TEAM, AWAY_TEAM, DRAW
  af_fixture_id integer,
  updated_at timestamptz not null default now()
);
create index fixtures_utc_date_idx on fixtures (utc_date);
create index fixtures_competition_idx on fixtures (competition_id, utc_date);
create index fixtures_af_idx on fixtures (af_fixture_id);

create table standings (
  competition_id integer not null references competitions(id),
  season integer not null,
  type text not null default 'TOTAL',   -- TOTAL, HOME, AWAY
  grp text not null default '',         -- group name for cups, empty for leagues
  position integer not null,
  team_id integer not null references teams(id),
  played integer not null default 0,
  won integer not null default 0,
  draw integer not null default 0,
  lost integer not null default 0,
  points integer not null default 0,
  goals_for integer not null default 0,
  goals_against integer not null default 0,
  goal_difference integer not null default 0,
  form text,
  updated_at timestamptz not null default now(),
  primary key (competition_id, season, type, grp, position)
);

-- One row per fixture that API-Football has told us about while live or after.
create table live_state (
  fixture_id integer primary key references fixtures(id) on delete cascade,
  af_fixture_id integer,
  status_short text not null,      -- API-Football: NS, 1H, HT, 2H, ET, P, FT, AET, PEN, ...
  elapsed integer,
  extra integer,
  home_goals integer,
  away_goals integer,
  updated_at timestamptz not null default now()
);

create table events (
  id bigint generated always as identity primary key,
  fixture_id integer not null references fixtures(id) on delete cascade,
  dedupe_key text not null,
  minute integer not null,
  extra_minute integer,
  type text not null,              -- Goal, Card, subst, Var
  detail text,                     -- Normal Goal, Penalty, Yellow Card, Red Card, ...
  team_id integer references teams(id),
  player_name text,
  assist_name text,
  comments text,
  unique (fixture_id, dedupe_key)
);
create index events_fixture_idx on events (fixture_id, minute);

create table lineups (
  fixture_id integer not null references fixtures(id) on delete cascade,
  team_id integer not null references teams(id),
  formation text,
  coach text,
  starters jsonb not null default '[]',
  substitutes jsonb not null default '[]',
  updated_at timestamptz not null default now(),
  primary key (fixture_id, team_id)
);

-- Raw upstream responses, keyed by source + path + params. Reads hit this first, so API usage follows the clock.
create table api_cache (
  key text primary key,
  source text not null,
  payload jsonb not null,
  fetched_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index api_cache_expires_idx on api_cache (expires_at);

-- Request counters per source and time bucket ('day:2026-10-20', 'min:2026-10-20T10:15').
create table api_usage (
  source text not null,
  bucket text not null,
  count integer not null default 0,
  primary key (source, bucket)
);

-- Atomic budget check: increments and returns true only when the bucket is still under the limit.
create function bump_usage(p_source text, p_bucket text, p_limit integer)
returns boolean
language plpgsql
as $$
declare
  new_count integer;
begin
  insert into api_usage (source, bucket, count) values (p_source, p_bucket, 1)
  on conflict (source, bucket) do update set count = api_usage.count + 1
    where api_usage.count < p_limit
  returning count into new_count;
  return new_count is not null;
end;
$$;
