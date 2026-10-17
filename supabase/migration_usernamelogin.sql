-- TrackMoney v1.1: username-login RPC (run AFTER schema.sql).
-- Needed because anonymous (pre-login) clients cannot SELECT profiles
-- directly under RLS, so the app resolves username -> email via this
-- SECURITY DEFINER function instead.

create or replace function public.lookup_email_by_username(p_username text)
returns text language plpgsql security definer set search_path = public as $$
declare v_email text;
begin
  select p.email into v_email from public.profiles p
  where p.username = lower(trim(p_username));
  return v_email;
end $$;
