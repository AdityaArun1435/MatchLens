-- Scheduled refresh: pg_cron calls the Vercel Python function every minute through pg_net.
-- Why not Vercel cron: the Hobby plan allows one run per day. pg_cron on Supabase free allows every minute.
-- The URL and shared secret live in Supabase Vault, not in this file. Set them once with:
--   select vault.create_secret('https://<your-site>/api/refresh', 'refresh_url');
--   select vault.create_secret('<same value as CRON_SECRET in Vercel>', 'refresh_secret');
create extension if not exists pg_net;

create or replace function call_refresh() returns void
language plpgsql security definer set search_path = public, vault, net
as $$
declare
  u text;
  s text;
begin
  select decrypted_secret into u from vault.decrypted_secrets where name = 'refresh_url';
  select decrypted_secret into s from vault.decrypted_secrets where name = 'refresh_secret';
  if u is null or s is null then
    return;  -- not configured yet
  end if;
  perform net.http_post(
    url := u,
    headers := jsonb_build_object('Authorization', 'Bearer ' || s, 'Content-Type', 'application/json'),
    body := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
end;
$$;

revoke execute on function call_refresh() from public, anon, authenticated;

select cron.schedule('matchlens-refresh', '* * * * *', $$select call_refresh()$$);
