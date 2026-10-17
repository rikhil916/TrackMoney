-- TrackMoney v1.3: admin may act on behalf of GUEST members in settlement.
--
-- Problem: guests have no login, so a transfer where a guest is the payer or
-- the receiver could never be marked/confirmed — the trip could never reach
-- "Fully Settled". Spec: the admin collects or confirms guest payments.
-- Fix: for guest-side transfers, the trip ADMIN gets the same buttons
-- (enforced here in the DB, not just in the UI).
--
-- Run AFTER schema.sql in the Supabase SQL editor.

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
