-- The website reads with the publishable (anon) key. Writes and the cache tables are service-role only.
alter table competitions enable row level security;
alter table teams enable row level security;
alter table fixtures enable row level security;
alter table standings enable row level security;
alter table live_state enable row level security;
alter table events enable row level security;
alter table lineups enable row level security;
alter table api_cache enable row level security;
alter table api_usage enable row level security;

create policy "public read" on competitions for select using (true);
create policy "public read" on teams for select using (true);
create policy "public read" on fixtures for select using (true);
create policy "public read" on standings for select using (true);
create policy "public read" on live_state for select using (true);
create policy "public read" on events for select using (true);
create policy "public read" on lineups for select using (true);
-- api_cache and api_usage: no policies, so only the service role can touch them.

revoke execute on function bump_usage(text, text, integer) from public, anon, authenticated;
