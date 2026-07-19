# patungandigital.id — PRD

## Original problem statement
Website for legal premium subscription sharing (patungan) — YouTube, Netflix, Spotify, extensible. Three views: Homepage, User Dashboard, Admin Dashboard. Admin manages users + services + host/regular slots + payment reminders (email + WhatsApp) + payment gateway (Xendit).

## User Choices
- Auth: JWT-based custom auth (email + password)
- Payment Gateway: Xendit (best-effort — invoice link created when XENDIT_API_KEY set)
- Reminder: SendGrid (email) + Twilio (WhatsApp) — MOCKED until keys provided
- Receipt storage: base64 in MongoDB
- Language: Bahasa Indonesia
- Design: Neo-Brutalist / Commercial Brutalism (cream bg, hard borders, solid shadows)

## Personas
- **Admin** (owner) — seeds admin/admin123; manages all users, services, plans, subscriptions, payments, reminder config, sends manual reminders.
- **Regular user** — registers, views own subs & payments, uploads receipt, edits profile, changes password.

## Core requirements (static)
- CRUD: users, services, service plans (host/regular slot count), subscriptions (user assigned to service with role host/regular), payments (per-subscription per-period).
- Homepage lists active services with price + min duration.
- Receipt upload with timestamp shown to admin.
- Reminder engine (config: days_before_due, enable_email, enable_whatsapp, template).

## Implemented (2026-02-18)
- Backend `server.py`: JWT auth (register/login/logout/me/profile/change-password), public /services, admin CRUD (users, services, plans, subscriptions, payments), user endpoints (/me/subscriptions, /me/payments, /me/payments/{id}/receipt), reminder-config + send-reminder (MOCKED without keys), Xendit invoice best-effort, stats endpoint.
- Frontend routes: `/`, `/login`, `/register`, `/dashboard/*`, `/admin/*`.
- Homepage with hero, bento service grid, how-it-works.
- UserDashboard: 4 tabs (Langganan, Pembayaran, Profil, Password) + base64 receipt upload.
- AdminDashboard: 6 tabs (Overview stats, Users, Services w/ Plans modal, Subscriptions, Payments w/ receipt viewer + status + manual reminder, Reminder Config).
- Seeded services (Netflix, Spotify, YouTube) with default plans.
- Testing agent: 25/25 backend tests pass, frontend smoke flows verified.

## Iteration 2 (2026-02-18) — Admin dashboard enhancements
- **Activity Log** (new tab): `admin_logs` collection auto-populated by `log_admin_action()` on create_user, delete_user, create_service, delete_service, delete_subscription, send_reminder, scheduler_run, bulk_delete_users, bulk_send_reminder, export_users_csv, export_payments_csv. UI shows actor, action badge, target, meta.
- **Auto Scheduler**: `_reminder_scheduler_loop` background asyncio task started in lifespan; runs every 1h; scans payments due in ≤ `days_before_due` days (from reminder_config) that haven't been reminded in last 24h; sends via same core `_send_reminder_for_payment` (MOCKED without keys). Manual trigger endpoint `POST /admin/scheduler/run-now` + UI button.
- **Bulk Actions + CSV Export**:
  - `POST /admin/users/bulk-delete` (skips admins) — UI checkboxes + "Hapus N" button.
  - `POST /admin/payments/bulk-remind` — UI checkboxes + "Kirim reminder N" button.
  - `GET /admin/users/export.csv` — streamed CSV with attachment header.
  - `GET /admin/payments/export.csv` — streamed CSV.
- Refactored `send_reminder` into `_send_reminder_for_payment` core (async run_in_executor for blocking SDK calls).
- Testing: 36/36 backend tests pass (11 new), all frontend flows verified.

## Iteration 3 (2026-02-18) — Auth, payments, analytics, filters
- **Emergent Google Login** (P1): "Lanjut/Daftar dengan Google" button on Login + Register pages. Redirects to `auth.emergentagent.com` with `window.location.origin + /dashboard`. `POST /api/auth/google/exchange` calls Emergent `/session-data`, finds/creates user by email in existing `users` collection, sets both `session_token` (7d, samesite=none/secure) and our own JWT `access_token` cookies. `get_current_user` now supports both cookies + Bearer header.
- **Xendit Webhook** (P1): `POST /api/webhooks/xendit` with X-CALLBACK-TOKEN verification (when `XENDIT_WEBHOOK_TOKEN` env set), parses `external_id=pay-<payment_id>` + `status`, auto-marks payment `paid` (on PAID/SETTLED) or `overdue` (on EXPIRED/FAILED); logs to activity log as `xendit_webhook`.
- **BSON date migration** (P2): startup migration converts existing string `due_date` and `last_reminder_at` to native BSON datetime; new writes use datetime directly; `_run_due_reminders` compares native datetime; auto-serialized to ISO string on API responses.
- **Live Analytics** (P3): `GET /api/admin/analytics` returns {monthly (12 mo timeline with ID month labels), by_service (revenue per service, sorted), status_distribution, totals}. Admin Overview renders Recharts LineChart (monthly revenue) + BarChart (revenue per service) + 3 metric cards.
- **Search + Filter** (P4): SearchInput component with clear button on Users, Payments (+ status dropdown), Subscriptions tabs. useMemo-based client-side filter across relevant text fields.
- Testing: 45/45 backend tests PASS (9 new), all frontend flows verified. No regressions.

## Iteration 4 (2026-02-19) — Midtrans, Referral, Split, Analytics optimization
- **Midtrans (P0)**: Replaced Xendit. Server/Client/Merchant keys in `backend/.env`. `admin_create_payment` calls Midtrans Snap `/snap/v1/transactions` → stores `midtrans_token` + `midtrans_redirect_url`. `POST /api/webhooks/midtrans` verifies SHA512 signature, maps `settlement`/`capture+accept` → paid, `cancel/deny/expire/failure` → overdue. User's payment card shows "Bayar via Midtrans" button. Xendit webhook kept for backward compat.
- **Referral (P3)**:
  - `user.referral_code` (unique, auto-generated on register/first login), `user.referred_by`, `user.referral_credit`, `user.first_paid_at`.
  - `POST /api/auth/register` accepts optional `referral_code`; Register page autofills from `?ref=CODE` URL param.
  - On admin update payment status → `paid`, `apply_referral_rewards_if_first_paid` credits Rp 10.000 to BOTH users (idempotent via `first_paid_at`).
  - On `admin_create_payment`, if user has `referral_credit > 0`, auto-subtract from amount (payment stores `referral_credit_applied` for admin visibility).
  - New collection `referral_rewards` tracks each reward event.
  - `GET /api/me/referral-stats` returns code/credit/invited/earned/referred_by.
  - New ReferralPanel tab in UserDashboard with copy code, copy link (`?ref=`), WhatsApp share button.
- **Split AdminDashboard (P2)**: 916 → 75 lines orchestrator. Extracted to `/pages/admin/OverviewTab.jsx`, `UsersTab.jsx`, `ServicesTab.jsx`, `SubscriptionsTab.jsx`, `PaymentsTab.jsx`, `ReminderTab.jsx`, `ActivityTab.jsx`, `shared.jsx` (Modal/F/SearchInput/Note).
- **Analytics $lookup (P2)**: Single aggregation pipeline joins payments→subscriptions→services in one round-trip instead of N+1 Python loop.
- Testing: 55/55 backend tests PASS (10 new). All frontend flows verified. No bugs.

## Iteration 5 (2026-02-19) — Referral banner, Leaderboard, Tier Rewards
- **Homepage referral banner**: Full-width `#FFD60A` section with "Ajak teman → Rp 10.000" headline, tier chips (5/10/25), CTA to Register, and inline top-5 monthly leaderboard sourced from `/api/leaderboard`.
- **Tier reward system**: `TIER_THRESHOLDS = [1→5refs/1mo, 2→10refs/2mo, 3→25refs/5mo]`. `maybe_grant_tier_rewards()` invoked after every successful referral; grants missing tiers idempotently via `$addToSet` on `tiers_granted` and `$inc` on `free_months_credit`. Logs `referral_reward` rows (type=tier_N) + activity log entry.
- **Free months consumption**: `admin_create_payment` prioritises `free_months_credit` (sets amount=0) before `referral_credit`; admin PaymentsTab renders "FREE MONTH" badge.
- **Public leaderboard endpoint**: `GET /api/leaderboard` returns `{monthly, all_time, month_label}` via a 2-stage aggregation on `referral_rewards` (excludes tier rows via `referred_id != null`). Each row has rank/name/initials/count/total_earned/tiers_granted.
- **Extended /me/referral-stats**: adds `free_months_credit`, `successful_count`, `tiers`, `tiers_granted`, `next_tier`. ReferralPanel now shows tier progress bar with % to next unlock + all-time & monthly leaderboard lists.
- **Fixed** `gen_referral_code` to always yield exactly 8 chars (increased URL-safe entropy pool).
- Testing: 63/64 backend tests PASS (9/9 iter5 new). Frontend flows verified.

## Backlog / next tasks
- **P0** (external): User setup — Midtrans Dashboard → Settings → Payment → Notification URL: `https://group-stream-admin.preview.emergentagent.com/api/webhooks/midtrans`.
- **P1**: Real SendGrid + Twilio keys to enable live email/WhatsApp.
- **P2**: Split `server.py` (1364 lines) into `routers/*.py` modules (referral, admin, midtrans, analytics).
- **P2**: DB cleanup / filter test-prefixed users from public leaderboard before production launch.
- **P2**: Remove deprecated Xendit endpoints once Midtrans is live-verified.
- **P2**: Move base64 receipts to object storage.
