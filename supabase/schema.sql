set check_function_bodies = off;
-- TrackMoney: Cloud Accounts + Shared Trip Planner (v1)
-- Paste this whole file into the Supabase SQL editor and run it once.
-- Assumes the default `auth.users` table exists (Supabase Auth).
-- All money is stored as INTEGER paise. Format as ₹ only for display.
--
-- Tables: profiles, trips, trip_members, trip_invites,
--         trip_expenses, expense_splits, settlements

-- ============================================================ extensions --
create extension if not exists "pgcrypto";

-- ============================================================ helpers --
-- True when the caller belongs to the trip (any role).
create or replace function public.is_trip_member(p_trip uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.trip_members m
    where m.trip_id = p_trip and m.user_id = auth.uid()
  );
$$;

-- True when the caller is an admin of the trip.
create or replace function public.is_trip_admin(p_trip uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.trip_members m
    where m.trip_id = p_trip and m.user_id = auth.uid() and m.role = 'admin'
  );
$$;

-- ============================================================ tables --

-- One row per auth user. Created at sign-up (see trigger below).
create table if not exists public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  name       text not null,
  username   text not null unique,
  phone      text not null unique,
  email      text unique,
  created_at timestamptz not null default now(),
  constraint username_fmt check (username ~ '^[a-z0-9_]{3,20}$'),
  constraint phone_fmt    check (phone ~ '^\+91[6-9][0-9]{9}$')
);
create index if not exists idx_profiles_username on public.profiles (username);
create index if not exists idx_profiles_phone    on public.profiles (phone);

create table if not exists public.trips (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (char_length(name) between 1 and 80),
  destination text,
  start_date  date not null default CURRENT_DATE,
  description text default '',
  status      text not null default 'open' check (status in ('open','closed')),
  join_code   text not null unique,
  code_enabled boolean not null default true,
  created_by  uuid not null references auth.users (id),
  created_at  timestamptz not null default now(),
  locked_at   timestamptz,
  constraint join_code_fmt check (join_code ~ '^[A-Z2-9]{6}$')
);
create index if not exists idx_trips_status     on public.trips (status);
create index if not exists idx_trips_created_by on public.trips (created_by);

-- Members: registered users (user_id set) or guests (guest_name set, user_id null).
create table if not exists public.trip_members (
  id           uuid primary key default gen_random_uuid(),
  trip_id      uuid not null references public.trips (id) on delete cascade,
  user_id      uuid references auth.users (id) on delete set null,
  guest_name   text,
  display_name text not null,
  phone        text,
  role         text not null default 'member' check (role in ('admin','member')),
  created_at   timestamptz not null default now(),
  constraint member_identity check (
    (user_id is not null and guest_name is null)
    or (user_id is null and guest_name is not null and char_length(guest_name) >= 1)
  ),
  constraint one_row_per_user unique (trip_id, user_id)
);
create index if not exists idx_members_trip on public.trip_members (trip_id);
create index if not exists idx_members_user on public.trip_members (user_id);

-- Pending invites keyed by normalized phone. Claimed automatically on sign-up.
create table if not exists public.trip_invites (
  id         uuid primary key default gen_random_uuid(),
  trip_id    uuid not null references public.trips (id) on delete cascade,
  phone      text not null check (phone ~ '^\+91[6-9][0-9]{9}$'),
  invited_by uuid references auth.users (id) on delete set null,
  status     text not null default 'pending' check (status in ('pending','accepted','expired')),
  created_at timestamptz not null default now()
);
create index if not exists idx_invites_trip  on public.trip_invites (trip_id);
create index if not exists idx_invites_phone on public.trip_invites (phone, status);

create table if not exists public.trip_expenses (
  id               uuid primary key default gen_random_uuid(),
  trip_id          uuid not null references public.trips (id) on delete cascade,
  title            text not null check (char_length(title) between 1 and 120),
  amount_paise     integer not null check (amount_paise > 0),
  expense_date     date not null default CURRENT_DATE,
  category         text not null default 'other'
                   check (category in ('food','travel','stay','shopping','activity','other')),
  paid_by_member   uuid not null references public.trip_members (id) on delete restrict,
  created_by       uuid not null references auth.users (id),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index if not exists idx_expenses_trip on public.trip_expenses (trip_id);
create index if not exists idx_expenses_date on public.trip_expenses (trip_id, expense_date desc);

create table if not exists public.expense_splits (
  expense_id      uuid not null references public.trip_expenses (id) on delete cascade,
  member_id       uuid not null references public.trip_members (id) on delete restrict,
  share_paise     integer not null check (share_paise >= 0),
  primary key (expense_id, member_id)
);
create index if not exists idx_splits_member on public.expense_splits (member_id);

create table if not exists public.settlements (
  id             uuid primary key default gen_random_uuid(),
  trip_id        uuid not null references public.trips (id) on delete cascade,
  from_member    uuid not null references public.trip_members (id) on delete restrict,
  to_member      uuid not null references public.trip_members (id) on delete restrict,
  amount_paise   integer not null check (amount_paise > 0),
  status         text not null default 'pending'
                 check (status in ('pending','paid','confirmed')),
  changed_by     uuid references auth.users (id),
  created_at     timestamptz not null default now(),
  marked_at      timestamptz,
  confirmed_at   timestamptz,
  constraint no_self_pay check (from_member <> to_member)
);
create index if not exists idx_settle_trip   on public.settlements (trip_id);
create index if not exists idx_settle_status on public.settlements (trip_id, status);

-- ============================================================ constraints --
-- Split shares must add up exactly to the expense total. Enforced by trigger
-- (a CHECK cannot see other rows).
create or replace function public.check_split_sum()
returns trigger language plpgsql as $$
declare
  v_total integer;
  v_sum   integer;
begin
  select amount_paise into v_total
  from public.trip_expenses where id = coalesce(new.expense_id, old.expense_id);
  select coalesce(sum(share_paise), 0) into v_sum
  from public.expense_splits
  where expense_id = coalesce(new.expense_id, old.expense_id);
  if v_sum <> v_total then
    raise exception 'splits (%) must sum to expense total (%)', v_sum, v_total;
  end if;
  return coalesce(new, old);
end $$;

drop trigger if exists trg_check_split_sum on public.expense_splits;
create constraint trigger trg_check_split_sum
  after insert or update or delete on public.expense_splits
  deferrable initially deferred
  for each row execute function public.check_split_sum();

-- No expense changes once the trip is closed (settlement statuses still move).
create or replace function public.lock_expenses_when_closed()
returns trigger language plpgsql as $$
declare v_status text;
begin
  select status into v_status from public.trips
  where id = coalesce(new.trip_id, old.trip_id);
  if v_status = 'closed' then
    raise exception 'trip is closed: expenses are locked';
  end if;
  return coalesce(new, old);
end $$;

drop trigger if exists trg_lock_expenses on public.trip_expenses;
create trigger trg_lock_expenses
  before insert or update or delete on public.trip_expenses
  for each row execute function public.lock_expenses_when_closed();

drop trigger if exists trg_lock_splits on public.expense_splits;
create trigger trg_lock_splits
  before insert or update or delete on public.expense_splits
  for each row execute function public.lock_expenses_when_closed();

-- Keep updated_at fresh.
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists trg_touch_expense on public.trip_expenses;
create trigger trg_touch_expense
  before update on public.trip_expenses
  for each row execute function public.touch_updated_at();

-- ============================================================ RLS --
alter table public.profiles        enable row level security;
alter table public.trips           enable row level security;
alter table public.trip_members    enable row level security;
alter table public.trip_invites    enable row level security;
alter table public.trip_expenses   enable row level security;
alter table public.expense_splits  enable row level security;
alter table public.settlements     enable row level security;

-- profiles: searchable by any logged-in user (needed for username/phone
-- lookup when adding members); edits only by the owner.
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles
  for select to authenticated using (true);
drop policy if exists profiles_insert on public.profiles;
create policy profiles_insert on public.profiles
  for insert to authenticated with check (id = auth.uid());
drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles
  for update to authenticated using (id = auth.uid());

-- trips: readable by members and by the creator (the creator needs to see
-- the row to bootstrap the first admin membership; see migration_bootstrap).
drop policy if exists trips_select on public.trips;
create policy trips_select on public.trips
  for select to authenticated
  using (public.is_trip_member(id) or created_by = auth.uid());
drop policy if exists trips_insert on public.trips;
create policy trips_insert on public.trips
  for insert to authenticated with check (created_by = auth.uid());
drop policy if exists trips_update on public.trips;
create policy trips_update on public.trips
  for update to authenticated
  using (public.is_trip_admin(id))
  with check (public.is_trip_admin(id));
-- No direct deletes: trips stay as history. Admins close them.

-- trip_members: visible to members; admin manages (insert/update/delete).
-- The creator bootstraps the first admin row via members_bootstrap below.
drop policy if exists members_select on public.trip_members;
create policy members_select on public.trip_members
  for select to authenticated using (public.is_trip_member(trip_id));
drop policy if exists members_admin_write on public.trip_members;
create policy members_admin_write on public.trip_members
  for all to authenticated
  using (public.is_trip_admin(trip_id))
  with check (public.is_trip_admin(trip_id));
drop policy if exists members_bootstrap on public.trip_members;
create policy members_bootstrap on public.trip_members
  for insert to authenticated
  with check (
    user_id = auth.uid()
    and exists (select 1 from public.trips t
                where t.id = trip_id and t.created_by = auth.uid())
  );

-- trip_invites: members can read/invite; admin can remove.
drop policy if exists invites_select on public.trip_invites;
create policy invites_select on public.trip_invites
  for select to authenticated using (public.is_trip_member(trip_id));
drop policy if exists invites_insert on public.trip_invites;
create policy invites_insert on public.trip_invites
  for insert to authenticated
  with check (public.is_trip_member(trip_id));
drop policy if exists invites_delete on public.trip_invites;
create policy invites_delete on public.trip_invites
  for delete to authenticated using (public.is_trip_admin(trip_id));

-- trip_expenses: members read; any member can add; only the author or an
-- admin can edit/delete, and only while the trip is open (see trigger).
drop policy if exists expenses_select on public.trip_expenses;
create policy expenses_select on public.trip_expenses
  for select to authenticated using (public.is_trip_member(trip_id));
drop policy if exists expenses_insert on public.trip_expenses;
create policy expenses_insert on public.trip_expenses
  for insert to authenticated
  with check (public.is_trip_member(trip_id) and created_by = auth.uid());
drop policy if exists expenses_update on public.trip_expenses;
create policy expenses_update on public.trip_expenses
  for update to authenticated
  using (public.is_trip_member(trip_id)
         and (created_by = auth.uid() or public.is_trip_admin(trip_id)));
drop policy if exists expenses_delete on public.trip_expenses;
create policy expenses_delete on public.trip_expenses
  for delete to authenticated
  using (public.is_trip_member(trip_id)
         and (created_by = auth.uid() or public.is_trip_admin(trip_id)));

-- expense_splits: same visibility as their expense; writes ride with the
-- expense write (trigger re-checks the trip lock).
drop policy if exists splits_select on public.expense_splits;
create policy splits_select on public.expense_splits
  for select to authenticated using (
    exists (select 1 from public.trip_expenses e
            where e.id = expense_id and public.is_trip_member(e.trip_id))
  );
drop policy if exists splits_write on public.expense_splits;
create policy splits_write on public.expense_splits
  for all to authenticated using (
    exists (select 1 from public.trip_expenses e
            where e.id = expense_id and public.is_trip_member(e.trip_id))
  ) with check (
    exists (select 1 from public.trip_expenses e
            where e.id = expense_id and public.is_trip_member(e.trip_id))
  );

-- settlements: members read; rows are written by end_trip / payment RPCs.
drop policy if exists settle_select on public.settlements;
create policy settle_select on public.settlements
  for select to authenticated using (public.is_trip_member(trip_id));
-- No direct insert/update/delete: all writes go through RPCs below.

-- ============================================================ RPC --
-- Join-code lookup + join (so users can find a trip by code without a broad
-- SELECT policy on trips).
create or replace function public.lookup_trip_by_code(p_code text)
returns table (trip_id uuid, name text, destination text, member_count bigint)
language plpgsql security definer set search_path = public as $$
begin
  return query
  select t.id, t.name, t.destination, count(m.id)
  from public.trips t left join public.trip_members m on m.trip_id = t.id
  where t.join_code = upper(trim(p_code)) and t.code_enabled
    and t.status = 'open'
  group by t.id;
end $$;

create or replace function public.join_trip_by_code(p_code text)
returns uuid language plpgsql security definer set search_path = public as $$
declare v_trip uuid; v_name text;
begin
  select t.id into v_trip from public.trips t
  where t.join_code = upper(trim(p_code)) and t.code_enabled
    and t.status = 'open';
  if v_trip is null then
    raise exception 'invalid or disabled join code';
  end if;
  if public.is_trip_member(v_trip) then return v_trip; end if;
  select p.name into v_name from public.profiles p where p.id = auth.uid();
  insert into public.trip_members (trip_id, user_id, display_name, role)
  values (v_trip, auth.uid(), coalesce(v_name, 'Member'), 'member')
  on conflict (trip_id, user_id) do nothing;
  return v_trip;
end $$;

-- Called after sign-up / login: attach the user to every trip that invited
-- their phone number while they were unregistered.
create or replace function public.claim_phone_invites()
returns integer language plpgsql security definer set search_path = public as $$
declare v_phone text; v_name text; v_n integer := 0;
begin
  select p.phone, p.name into v_phone, v_name
  from public.profiles p where p.id = auth.uid();
  if v_phone is null then return 0; end if;
  insert into public.trip_members (trip_id, user_id, display_name, phone, role)
  select i.trip_id, auth.uid(), coalesce(v_name, 'Member'), v_phone, 'member'
  from public.trip_invites i
  where i.phone = v_phone and i.status = 'pending'
  on conflict (trip_id, user_id) do nothing;
  get diagnostics v_n = row_count;
  update public.trip_invites set status = 'accepted'
  where phone = v_phone and status = 'pending';
  return v_n;
end $$;

-- Admin ends the trip: locks expenses (status='closed'). The app then
-- computes settlements with backend/settlement.py and stores them via
-- record_settlements() in the same flow.
create or replace function public.end_trip(p_trip uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_trip_admin(p_trip) then
    raise exception 'only an admin can end the trip';
  end if;
  update public.trips set status = 'closed', locked_at = now()
  where id = p_trip and status = 'open';
end $$;

-- Store a freshly computed settlement plan (admin only, right after end_trip,
-- exactly once). The app deletes nothing; this RPC replaces any draft rows.
create or replace function public.record_settlements(
  p_trip uuid, p_items jsonb
) returns integer language plpgsql security definer set search_path = public as $$
declare v_n integer := 0; item jsonb;
begin
  if not public.is_trip_admin(p_trip) then
    raise exception 'only an admin can record settlements';
  end if;
  delete from public.settlements
  where trip_id = p_trip and status = 'pending';
  for item in select * from jsonb_array_elements(p_items) loop
    insert into public.settlements
      (trip_id, from_member, to_member, amount_paise, status)
    values (p_trip,
            (item->>'from_member')::uuid,
            (item->>'to_member')::uuid,
            (item->>'amount_paise')::int, 'pending');
    v_n := v_n + 1;
  end loop;
  return v_n;
end $$;

-- Payment status flow, enforced in the database (not just the UI):
--   pending -> paid      (only the PAYER's user can mark)
--   paid    -> confirmed (only the RECEIVER's user can confirm)
--   paid    -> pending   (only the RECEIVER can reject)
create or replace function public.mark_settlement_paid(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare v_from uuid; v_status text;
begin
  select from_member, status into v_from, v_status
  from public.settlements where id = p_id;
  if v_from is null then raise exception 'settlement not found'; end if;
  if v_status <> 'pending' then raise exception 'only pending can be marked paid'; end if;
  if not exists (select 1 from public.trip_members m
                 where m.id = v_from and m.user_id = auth.uid()) then
    raise exception 'only the payer can mark as paid';
  end if;
  update public.settlements
  set status = 'paid', marked_at = now(), changed_by = auth.uid()
  where id = p_id;
end $$;

create or replace function public.confirm_settlement(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare v_to uuid; v_status text;
begin
  select to_member, status into v_to, v_status
  from public.settlements where id = p_id;
  if v_to is null then raise exception 'settlement not found'; end if;
  if v_status <> 'paid' then raise exception 'only paid can be confirmed'; end if;
  if not exists (select 1 from public.trip_members m
                 where m.id = v_to and m.user_id = auth.uid()) then
    raise exception 'only the receiver can confirm';
  end if;
  update public.settlements
  set status = 'confirmed', confirmed_at = now(), changed_by = auth.uid()
  where id = p_id;
end $$;

create or replace function public.reject_settlement(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare v_to uuid; v_status text;
begin
  select to_member, status into v_to, v_status
  from public.settlements where id = p_id;
  if v_to is null then raise exception 'settlement not found'; end if;
  if v_status <> 'paid' then raise exception 'only paid can be rejected'; end if;
  if not exists (select 1 from public.trip_members m
                 where m.id = v_to and m.user_id = auth.uid()) then
    raise exception 'only the receiver can reject';
  end if;
  update public.settlements
  set status = 'pending', marked_at = null, changed_by = auth.uid()
  where id = p_id;
end $$;

-- Username -> email resolution for pre-login clients (anon cannot SELECT
-- profiles under RLS, so this SECURITY DEFINER function does the lookup).
create or replace function public.lookup_email_by_username(p_username text)
returns text language plpgsql security definer set search_path = public as $$
declare v_email text;
begin
  select p.email into v_email from public.profiles p
  where p.username = lower(trim(p_username));
  return v_email;
end $$;

-- Auto-claim phone invites right after a profile row appears (covers the
-- "signed up with an invited number" flow even if the app forgets to call it).
create or replace function public.after_profile_claim()
returns trigger language plpgsql security definer set search_path = public as $$
declare v_n integer := 0;
begin
  insert into public.trip_members (trip_id, user_id, display_name, phone, role)
  select i.trip_id, new.id, coalesce(new.name, 'Member'), new.phone, 'member'
  from public.trip_invites i
  where i.phone = new.phone and i.status = 'pending'
  on conflict (trip_id, user_id) do nothing;
  get diagnostics v_n = row_count;
  update public.trip_invites set status = 'accepted'
  where phone = new.phone and status = 'pending';
  return new;
end $$;

drop trigger if exists trg_profile_claim on public.profiles;
create trigger trg_profile_claim
  after insert on public.profiles
  for each row execute function public.after_profile_claim();

-- ============================================================ settlement v1.3 (guest support) --
-- Re-defines the three payment RPCs so the trip ADMIN can act for GUEST
-- members (guests have no login). Last definitions win — keep in sync with
-- supabase/migration_guest_settlement.sql for existing databases.

create or replace function public.mark_settlement_paid(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare v_from uuid; v_status text; v_trip uuid; v_payer_guest boolean;
begin
  select from_member, status, trip_id into v_from, v_status, v_trip
  from public.settlements where id = p_id;
  if v_from is null then raise exception 'settlement not found'; end if;
  if v_status <> 'pending' then raise exception 'only pending can be marked paid'; end if;
  select (m.user_id is null) into v_payer_guest
  from public.trip_members m where m.id = v_from;
  if not (
       exists (select 1 from public.trip_members m
               where m.id = v_from and m.user_id = auth.uid())
       or (v_payer_guest and public.is_trip_admin(v_trip))
     ) then
    raise exception 'only the payer can mark as paid';
  end if;
  update public.settlements
  set status = 'paid', marked_at = now(), changed_by = auth.uid()
  where id = p_id;
end $$;

create or replace function public.confirm_settlement(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare v_to uuid; v_status text; v_trip uuid; v_recv_guest boolean;
begin
  select to_member, status, trip_id into v_to, v_status, v_trip
  from public.settlements where id = p_id;
  if v_to is null then raise exception 'settlement not found'; end if;
  if v_status <> 'paid' then raise exception 'only paid can be confirmed'; end if;
  select (m.user_id is null) into v_recv_guest
  from public.trip_members m where m.id = v_to;
  if not (
       exists (select 1 from public.trip_members m
               where m.id = v_to and m.user_id = auth.uid())
       or (v_recv_guest and public.is_trip_admin(v_trip))
     ) then
    raise exception 'only the receiver can confirm';
  end if;
  update public.settlements
  set status = 'confirmed', confirmed_at = now(), changed_by = auth.uid()
  where id = p_id;
end $$;

create or replace function public.reject_settlement(p_id uuid)
returns void language plpgsql security definer set search_path = public as $$
declare v_to uuid; v_status text; v_trip uuid; v_recv_guest boolean;
begin
  select to_member, status, trip_id into v_to, v_status, v_trip
  from public.settlements where id = p_id;
  if v_to is null then raise exception 'settlement not found'; end if;
  if v_status <> 'paid' then raise exception 'only paid can be rejected'; end if;
  select (m.user_id is null) into v_recv_guest
  from public.trip_members m where m.id = v_to;
  if not (
       exists (select 1 from public.trip_members m
               where m.id = v_to and m.user_id = auth.uid())
       or (v_recv_guest and public.is_trip_admin(v_trip))
     ) then
    raise exception 'only the receiver can reject';
  end if;
  update public.settlements
  set status = 'pending', marked_at = null, changed_by = auth.uid()
  where id = p_id;
end $$;
