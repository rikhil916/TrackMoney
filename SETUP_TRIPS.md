# TrackMoney — Cloud Accounts + Shared Trip Planner (Setup & Run)

Personal features (categories, entries, dashboard) stay in local SQLite,
scoped per logged-in user (`user_id`; logged-out uses `local`).
Trips live in Supabase (Postgres + Auth). UI imports only from `backend/`.

## 1. Create the Supabase project
1. Go to https://supabase.com → New project. Save the DB password.
2. Project Settings → API: copy **Project URL** and **anon public key**
   (never use `service_role` in the app).
3. Authentication → Sign In / Sign Up: enable **Email** provider;
   turn **Confirm email** ON (v1 requires email confirmation, no SMS OTP).

## 2. Create tables + RLS + RPCs (one paste)
1. Open the Supabase **SQL editor** → New query.
2. Paste the whole `supabase/schema.sql` from this repo → Run.
   It creates `profiles, trips, trip_members, trip_invites, trip_expenses,
   expense_splits, settlements`, indexes, constraints (splits must sum to the
   expense total; no expense edits after close), RLS policies, and RPCs
   (`lookup_trip_by_code, join_trip_by_code, claim_phone_invites, end_trip,
   record_settlements, mark_settlement_paid, confirm_settlement,
   reject_settlement`).

## 3. Configure the app
```bash
cd TrackMoney
cp .env.example .env
# edit .env: SUPABASE_URL + SUPABASE_ANON_KEY
.venv/bin/pip install -r requirements.txt
```

## 4. Run
```bash
# desktop / web
.venv/bin/flet run main.py
# or web on a port:
.venv/bin/flet run --web --port 8580 main.py
# android
flet build apk
```

## 5. First use
1. Open the app → **Trips** tab → Create account (name, username 3–20
   lowercase, +91 phone, email, password 8+). Confirm the email, then log in
   (email or username).
2. Without `.env`, the Trips tab shows an offline notice; personal tabs keep
   working. Every cloud error shows a retry path ("No internet…" otherwise).
3. Each phone logs in separately and sees the same trips (5s poll +
   pull-to-refresh; polling stops when you leave the screen).

## 6. Key flows
- **Create trip** (FAB on Trips tab) → admin + 6-char code.
- **Add members**: search username/phone → instant; unknown phone → pending
  invite auto-claimed at sign-up (DB trigger + `claim_phone_invites` RPC);
  join code (admin can disable); guest (name only, admin pays/collects).
- **Expenses**: title, ₹ amount (stored as integer paise), date, category,
  payer, split among — equal (remainder paise to earliest members) or custom
  (must total exactly). Only author/admin edits, only while open.
- **End trip** (admin): `end_trip()` locks expenses, greedy settlement
  (`backend/settlement.py`) is recorded via `record_settlements()` in the
  same flow.
- **Payments**: payer marks paid → receiver confirms/rejects (Pending →
  Paid → Confirmed), enforced by RPCs (not just UI); `changed_by` + timestamps
  recorded. All confirmed → Fully Settled. Tab dot (Trips •) marks action
  needed.

## 7. Tests
```bash
.venv/bin/python -c "
import backend.tests.test_settlement as t
for n in [x for x in dir(t) if x.startswith('test_')]:
    getattr(t,n)(); print('PASS',n)"
.venv/bin/python /tmp/tm_test.py  # 19 local integration tests
```
Covers: 3-member uneven, 4-member + guest, indivisible amounts, greedy
minimality, paise formatting/parsing.
