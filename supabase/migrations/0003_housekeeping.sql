-- Keep the cache and counters small. pg_cron runs on the Supabase free plan.
create extension if not exists pg_cron;

select cron.schedule('purge-api-cache', '17 * * * *',
  $$delete from api_cache where expires_at < now() - interval '1 day'$$);

select cron.schedule('purge-api-usage', '23 3 * * *',
  $$delete from api_usage
    where (bucket like 'min:%' and bucket < 'min:' || to_char(now() at time zone 'utc' - interval '1 day', 'YYYY-MM-DD"T"HH24:MI'))
       or (bucket like 'day:%' and bucket < 'day:' || to_char(now() at time zone 'utc' - interval '7 days', 'YYYY-MM-DD'))$$);
