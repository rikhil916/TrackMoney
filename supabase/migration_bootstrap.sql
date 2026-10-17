-- TrackMoney v1.2: let the trip creator bootstrap (run AFTER schema.sql).
--
-- Problem: INSERT ... RETURNING needs a matching SELECT policy, and the
-- creator is not a member yet — so creating a trip failed RLS twice:
--   1. the new trip row wasn't SELECT-visible to its creator;
--   2. the first (admin) member row failed the admin-only write policy.
-- Fix: creators can read trips they created, and can insert ONLY themselves
-- as a member of trips they created. Joining anyone else's trip still goes
-- through the admin policy or the join-code RPC.

drop policy if exists trips_select on public.trips;
create policy trips_select on public.trips
  for select to authenticated
  using (public.is_trip_member(id) or created_by = auth.uid());

drop policy if exists members_bootstrap on public.trip_members;
create policy members_bootstrap on public.trip_members
  for insert to authenticated
  with check (
    user_id = auth.uid()
    and exists (select 1 from public.trips t
                where t.id = trip_id and t.created_by = auth.uid())
  );
