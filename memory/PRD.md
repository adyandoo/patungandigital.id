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

## Iteration 6 (2026-02-19) — SendGrid, Router split, Cleanup, Onboarding
- **SendGrid key added** to `backend/.env`. Real email attempts on reminder send; falls back to log on unverified sender.
- **server.py split** (P1): extracted to `/app/backend/routers/analytics.py`, `referral.py`, `webhooks.py`. server.py 1364→1211 lines. Routers import from `server` at module load (circular-safe pattern since server includes them at end).
- **Cleanup endpoint** (P2): `POST /api/admin/cleanup-test-users?prefix=X` deletes users matching regex `^X` (case-insensitive), plus their subs/payments/referral_rewards; sets `referred_by=null` on remaining users pointing to deleted ones. Never touches admins. Overview tab has UI button.
- **Onboarding checklist** (P3): `GET /api/me/onboarding` returns 5-step progress {signup, profile-WA, first_payment, invite, reward} with percent. OnboardingCard renders above tabs with progress bar + step chips + smart "next action" button that switches to correct tab.
- **Bug fixes** (post-test): (a) `apply_referral_rewards_if_first_paid` now unconditionally sets `first_paid_at` on any first-paid payment (was gated on `referred_by` — broke organic-user onboarding). (b) Frontend OnboardingCard restored after truncation regression.
- Testing: **78/78 tests PASS** (11 iter6 + 3 iter6-retest new). Zero regressions.
- Cleanup: 111 test users removed post-test.

## Iteration 7 (2026-02-19) — Race-safe first_paid_at + Groups & Login Access + Waitlist
- **Race-safe first_paid_at (P2)**: `apply_referral_rewards_if_first_paid` uses atomic `update_one({"first_paid_at": None}, ...)` — `modified_count` decides the single "winner"; verified via `asyncio.gather` — 2 parallel PATCH status=paid produce exactly ONE referral_reward row + ONE +Rp10k credit increment on each side.
- **Groups + shared Login Access (P3)**:
  - New collections `groups` (per-service capacity bucket), `group_credentials` (email/password shared to group members).
  - Extended `SubscriptionInput` with optional `group_id`.
  - Admin endpoints: `GET/POST/PATCH/DELETE /api/admin/groups`; `PUT/GET/DELETE /api/admin/groups/{id}/credential`. List includes members with role + filled counts + credential (password masked).
  - User endpoint: `GET /api/me/groups` returns `[{group, service, role, members[{name,role,is_me}], credential{email,password,notes}}]` — password INCLUDED for members (that's the whole point of shared access).
  - Admin GroupsTab UI: card per group with slot bars, "Assign user" modal (patches subscription.group_id), "Set/Edit login" modal for credentials.
  - User Grup & Akses tab UI: header colored per service, member list with "(kamu)" marker, credential card with `Eye`/`EyeSlash` toggle + copy buttons for email & password.
- **Public slot availability + Waitlist (P4)**:
  - `GET /api/public/availability` (no auth) — per-service totals from groups + filled from group-assigned active subs, capped at total.
  - Home service cards: badge (`{X} tersedia` / `penuh`), slot bar (100% capped), "Antri di waitlist" replaces Register CTA when full.
  - `POST /api/waitlist` (no auth) creates entry; `GET/DELETE /api/admin/waitlist` admin-gated.
- Testing: **95/97 tests PASS** (9/9 iter7 new + 2 pre-existing scheduler flakes unrelated). All 4 features verified end-to-end.
- Cleanup: All iter7 test users + test services removed.

## Iteration 8 (2026-02-19) — Waitlist UI, Router split, Group status, Auto-suggest, H-7 expiry
- **Waitlist admin UI (P1)**: new tab [Waitlist] with entries table, mark-contacted (PATCH `/admin/waitlist/{id}` status='contacted'), delete. New endpoint `PATCH /api/admin/waitlist/{id}` accepts `{status, notes}`.
- **Groups extraction (P2)**: 12 endpoints (`/admin/groups`, `/admin/groups/{id}/credential`, `/me/groups`, `/public/availability`, `/waitlist`, `/admin/waitlist`, `/admin/groups/suggest`) moved to `routers/groups.py`. server.py 1408 → 1248 lines. Zero regressions.
- **Group status + expiry (P3)**: `GroupInput` gains `status` (active/paused/expired) + `expires_at`; GroupsTab modal shows both fields; card renders status badge + expiry chip.
- **Auto-suggest groups (P3)**: New `GET /api/admin/groups/suggest?service_id=X&role=Y` returns groups with open slots for the role. SubModal populates `[data-testid=submod-group]` dropdown with `"GroupName — X/Y regular, Z/W host — N slot regular tersedia"` format; shows red hint when no groups available.
- **H-7 expiry reminder (P3)**: scheduler tick scans groups with `expires_at within 7d + status=active + expiry_reminder_sent!=True`, sets flag idempotently and logs `group_expiry_reminder` activity entry.
- **E2E verified**: 1 Netflix group + 2 users (host+regular) assigned → set shared credential → both users see identical email/password via /me/groups. `is_me` flag correctly identifies self.
- Testing: **97/97 tests PASS** (10/10 iter8 new + full regression). One backend hardening applied by testing agent: `admin_list_subs` now ObjectId.is_valid guarded.

## Iteration 9 (2026-02-19) — Dual Payment Methods + Partial PATCH + Admin Seed + Orphan Cleanup
- **Dual payment methods (P0)**:
  - New `settings.payment_config` doc holds `qris_image_base64`, `qris_notes`, `manual_bank_info`, `midtrans_fee_percent` (default 5).
  - Public `GET /api/payment-config` (no auth) — used by user dashboard to render QRIS + fee copy.
  - Admin `GET/PUT /api/admin/payment-config` — new **Payment Config** tab in AdminDashboard (`data-testid=admin-tab-payment-settings`) lets admin upload QRIS image (base64), set instructions, manual bank info, and fee %.
  - `admin_create_payment` no longer auto-creates Midtrans snap. Payment starts with `payment_method=null`, `base_amount=original`.
  - New `POST /api/me/payments/{id}/choose-method` — user picks `qris` (0% fee, amount=base) or `midtrans` (adds fee=round(base*pct/100), creates Snap invoice on the fly, returns redirect_url). Ownership + status guarded. Returns 502 friendly error if Midtrans API rejects.
  - `upload_receipt` now **auto-approves** → sets `status='paid'` immediately (was 'review') and triggers referral rewards. Admin can still manually flip status back later.
  - UserDashboard `PaymentsPanel` refactored: shows method chooser buttons (`choose-qris-{id}`, `choose-midtrans-{id}`), QRIS modal with image + notes, upload-receipt button appears only after QRIS chosen, "Ganti metode" reset flow.
- **Partial subscription update (P1)**: New `SubscriptionUpdate` model (all Optional). `PATCH /admin/subscriptions/{id}` accepts any subset — e.g. just `{status:'paused'}` or `{group_id:'...'}`. Enables the auto-suggest group assignment flow to work without resending the full sub body.
- **Admin seeding & management (P2)**:
  - `.env` `ADMIN_PASSWORD` rotated to strong random `Adm!nPd-JavpOaidEa6wZgFnBS` (documented in `/app/memory/test_credentials.md`).
  - Seed logic **no longer force-resets** existing admin password on restart — so admins can change password via UserDashboard → Password tab and it persists across restarts.
  - New `POST /api/admin/create-admin` endpoint (admin-only) creates additional admin accounts. UI: yellow **Buat Admin** button in Users tab (`data-testid=admin-create-admin`) opens dedicated `AdminModal` with min-8-char password enforcement.
- **Legacy cleanup (P2)**: startup migration deletes orphan `subscriptions.user_id='0'` documents.
- Testing: **18/18 iter10 backend tests PASS** + frontend smoke confirmed (Payment Config tab, Buat Admin modal, QRIS/Midtrans buttons all interactive).
- **Not implemented** (deferred by user): WhatsApp / Twilio integration.

## Iteration 11 (2026-02-19) — Bulk User Import/Export + Auto-Invoice Generator + Field Bounds
- **P0: Bulk user import/export**:
  - `GET /api/admin/users/template.csv` — downloads template with 6 columns (name, email, username, whatsapp, gender, password) + 2 sample rows.
  - `POST /api/admin/users/import` — accepts `{file_base64, file_name}` (data URL or raw base64). Only `email` header is mandatory. Duplicate emails → `skipped[]`. Invalid emails → `errors[]`. Empty password → uses global default from `general_config`. Returns `{summary: {created, skipped, errors}}` for admin review.
  - `GET/PUT /api/admin/general-config` — new settings key with `default_new_user_password` (default `patungan123`, min 6 chars).
  - UI: Users tab now has three buttons: **Template CSV**, **Import CSV** (opens `ImportModal` with file picker + result panel showing per-row status), **Export CSV**. Password default is configurable in the new Auto Invoice tab.
- **P1: Auto-invoice generator**:
  - New `invoice_config` settings key: `{day_of_month(1-28), due_days(1-60), enabled}` with sensible defaults.
  - `_run_invoice_generator` runs every scheduler tick (hourly); on the configured `day_of_month`, iterates active subs and inserts pending payments (idempotent per subscription+period_label). New payments carry `auto_generated=true`.
  - `POST /api/admin/invoices/generate-now` — force trigger (ignores day-of-month gate but still idempotent). Perfect for onboarding new subs mid-month.
  - `GET/PUT /api/admin/invoice-config` endpoints for admin UI.
  - New **Auto Invoice** admin tab (`data-testid=admin-tab-auto-invoice`) with config form + manual **Generate invoice sekarang** button + default-password form.
- **P4: Field bounds**:
  - `midtrans_fee_percent` now bounded `Field(ge=0, le=100)` (422 on out-of-range).
  - `invoice_config.day_of_month` bounded `1-28` (avoids Feb edge case).
  - `invoice_config.due_days` bounded `1-60`.
  - `general_config.default_new_user_password` min 6 chars.
- **Deferred**: P2 (server.py refactor to `routers/payments.py` + `routers/settings.py`) — server.py now 1615 lines. P3 (object storage for base64 receipts + QRIS) — user chose to defer.
- **Testing**: 22/22 iter11 backend tests PASS + frontend smoke confirmed (Auto Invoice tab renders, Users import modal displays 3/0/0 result panel + toast). No regressions.

## Iteration 12 (2026-02-19) — Duration Flow + Password Reset + TZ-aware Scheduler + Refactor
- **P0 Subscription duration (per-payment)**:
  - New `Payment.duration_months` field (default 1, bounded 1–24). Admin picks duration when creating a payment (UI field in Payments modal + Auto-invoice inherits from `sub.duration_months`).
  - `extend_subscription_from_payment()` runs whenever a payment transitions to **paid** (via manual upload, admin PATCH, or Midtrans webhook). Sets `sub.start_date = first_paid_at` (only if empty/future), and extends `sub.end_date = max(current_end, now) + duration_months` using `dateutil.relativedelta`. Idempotent per payment via `applied_to_sub_at` flag.
  - `revert_subscription_extension()` runs when admin flips paid → non-paid (refund/reject) — rolls back the extension deterministically.
- **P0 Admin edits & password reset**:
  - Existing admin user modal continues to allow editing `name, email, username, whatsapp, gender, role` — password is NEVER shown or set by admin here.
  - New button per user row: **Reset password ke default** (data-testid `user-reset-pw-{id}`) → calls `POST /api/admin/users/{id}/reset-password`. Resets password to `general_config.default_new_user_password`, logs to admin_logs, sends SendGrid email (or mocks if key absent).
  - New **Forgot password** flow at login: `data-testid=forgot-password-link` opens `ForgotModal` → `POST /auth/forgot-password` (always 200, no enumeration). Token hashed SHA256, 1h expiry, stored in `db.password_resets`. Email link points to `/reset-password?token=xxx`.
  - New `/reset-password` route with token-based form → `POST /auth/reset-password` (verifies token, updates hash, marks used).
- **P1 Refactor**: server.py trimmed to 1683 lines (was 1854). New router files:
  - `routers/settings.py` — payment-config (public + admin), invoice-config, general-config.
  - `routers/admin_users.py` — bulk import CSV, template CSV, admin reset password.
  - Late-import pattern to avoid circular deps.
- **P2 TZ-aware scheduler**: `WIB = ZoneInfo("Asia/Jakarta")` (UTC+7 fallback). `_run_invoice_generator` now checks `now.astimezone(WIB).day` against `day_of_month`. Response includes `timezone: "Asia/Jakarta"`. Added `last_run_period_label` short-circuit — same-period hourly ticks are no-ops after first run. Storage remains UTC ISO strings.
- **P3 Payments filter**: `GET /api/admin/payments?auto_generated=true|false` + new dropdown `[payments-source-filter]` in Admin Payments tab (Semua | Auto-generated | Manual). Rows also show `auto` badge + duration badge (`3 bln`) when relevant.
- **Testing**: 16/16 iter12 backend PASS, frontend flows verified (100% success). No regressions.

## Iteration 13 (2026-02-19) — Testimonials + Profile Pics + Expiry Banner + WA Removal
- **WhatsApp removed (P1)**: All Twilio branches deleted from `_send_reminder`, `enable_whatsapp` unset on migration, ReminderTab checkbox removed, save payload no longer sends the field, scheduler summary no longer includes `whatsapp_sent`. WhatsApp phone number kept on user profile as contact only (not for notifications).
- **Expiry banner + Perpanjang (P2)**: `invoice_config.expiry_warning_days` (default 7, admin-tunable 1-30 via AutoInvoiceTab). New public `GET /api/payment-config` field surfaces this to users. UserDashboard SubsPanel renders a yellow warning banner when a sub's `end_date` is within N days, red banner when expired, both with **Perpanjang sekarang** button (`data-testid=renew-btn-{subId}`) → `POST /api/me/subscriptions/{id}/renew` creates a pending payment (`renew_by_user=true`, `duration_months` inherited from sub or override, amount = price × duration, period_label = next-period in WIB).
- **Testimonials (P3)**: New `routers/testimonials.py`:
  - Public `GET /api/testimonials` returns `{items, stats:{avg,count}}` — approved-only, with author name + `profile_picture_base64`, avg rounded to 2 decimals.
  - `POST /me/testimonials` (requires ≥1 subscription), `GET /me/testimonials`, `PATCH /me/testimonials/{id}` (blocks edits when already approved; edit resets to pending), `DELETE /me/testimonials/{id}` (allowed even for approved — user retracting).
  - `GET/PATCH/DELETE /admin/testimonials` — approve/reject/delete.
  - Rating bounded 1–5, comment 10–500 chars.
  - UI: **Testimoni** tab in UserDashboard (rating stars + textarea + own list with edit/delete). **Testimoni** tab in AdminDashboard (filter by status, approve/reject/delete). Homepage `testimonials-section` renders a marquee of approved cards + rating average badge (only visible if items exist).
- **Profile pictures (P4)**: `PUT /api/auth/profile-picture` accepts data URL (max ~500KB) or null to clear. Strict `data:image/` prefix validation. Client-side resize to 512×512 JPEG at q=0.85 before upload. New reusable **`Avatar`** component with deterministic initials-gradient fallback (8 curated palettes hashed from name). Placed in UserDashboard header + Profile tab + Testimoni cards + admin Testimonials tab + homepage marquee. Admin cannot set other users' pictures (per user choice).
- **Duration on subs (from testing agent feedback)**: `SubscriptionInput` + `SubscriptionUpdate` now accept `duration_months` (1–24). AdminDashboard Subscriptions modal has "Durasi default (bulan)" input. Auto-invoice generator now correctly carries this value into generated payments.
- **Onboarding checklist**: Step 2 label changed from "Lengkapi nomor WhatsApp" → "Lengkapi profil (nama, WhatsApp, gender)" and completes when either field is set — no longer WhatsApp-only gating.
- **Testing**: 15/15 iter13 backend tests PASS + frontend UI 100% verified. Minor issues flagged by testing agent were fixed same iteration (duration_months on sub, dead WA payload, whatsapp_sent key, image-only guard, onboarding label).

## Iteration 14 (2026-02-19) — About + Blog + Announcements + Rate-Limit + Date Picker
- **P2a Date picker (Shadcn Calendar + Indonesian locale)**:
  - New `DatePicker` component wraps Shadcn Calendar + Popover using `date-fns/locale/id`. Format: "19 Juli 2026". Clear button.
  - Replaces `<input type="date">` in AdminDashboard Payments modal (`pay-modal-due-date`) and Subscriptions modal (`sub-modal-start`, `sub-modal-end`).
- **P2b Refactor (conservative)**: Deferred to next iteration per user choice. server.py is now 1826 lines; extracted 6 routers (analytics, groups, referral, webhooks, testimonials, cms, settings, admin_users).
- **P3 Rate-limit forgot-password**: `POST /auth/forgot-password` now short-circuits if a token was issued for the same email within the last 5 minutes (checks `db.password_resets.created_at`). Response is still 200 (`rate_limited:true`) — no enumeration.
- **P4 About page**:
  - Public `GET /api/about` returns `{hero_title, story (markdown), mission (markdown), contact_email, contact_whatsapp, contact_address}` with sensible defaults.
  - Admin `PUT /api/admin/about` — new AboutTab in AdminDashboard for editing.
  - Public route `/about` renders hero + story (react-markdown + remark-gfm) + mission + contact cards + back-to-home CTA.
- **P5 Blog with markdown + tags + cover**:
  - Collection `blog_posts` with unique index on `slug`. Tags auto-lowercased on write.
  - Admin CRUD `/admin/blog` (create/list/edit/delete/toggle publish). Auto-slug from title with unique fallback (unix ts suffix). Duplicate slug on PATCH → 400.
  - Public `/blog` (paginated list with tag cloud) + `/blog/{slug}` (detail). Only `published:true` visible publicly.
  - Admin BlogTab modal has: title, slug (auto), tags (comma-sep), excerpt, cover image upload, markdown content with live preview toggle.
  - Tailwind Typography plugin added — markdown headings/lists/quotes now render with proper hierarchy.
- **P6 Announcements**:
  - Collection `announcements` with target: `all` | `service_ids` (multi-service). Severity: info | warning | critical. Optional `expires_at`.
  - Admin CRUD `/admin/announcements` with new AnnouncementsTab (form + list + edit + delete + service checkboxes).
  - User `GET /me/announcements` returns matching active + not-dismissed (or `?only_active=false` to include archive with `dismissed:true` flag). Scoping uses user's active subscriptions.
  - `POST /me/announcements/{id}/dismiss` adds user_id to `dismissed_by`.
  - UserDashboard: top-level `announcement-banners` strip on all tabs with severity color-coding + Tutup button; new "Pengumuman" tab shows archive (`announcements-panel`).
- **Navigation**: Navbar + footer now have Blog + Tentang links (data-testids `nav-blog`, `nav-about`, `footer-blog`, `footer-about`).
- **Testing**: 20/20 iter14 backend tests PASS + all frontend flows 100% verified.

## Iteration 15 (2026-02-19) — SEO + Sortable Tables + Auto-Assign Groups + Groups UX
- **P1 SEO** (react-helmet-async):
  - New `SEO` component sets `<title>`, `<meta name="description">`, Open Graph, Twitter Card, canonical, optional JSON-LD.
  - Home, About, Blog list, Blog detail all wrapped. Blog post emits Article JSON-LD (`headline, datePublished, author, publisher, keywords, mainEntityOfPage`).
  - Backend `GET /api/sitemap.xml` — dynamic sitemap listing `/`, `/about`, `/blog`, and every published post with `lastmod`. `GET /api/robots.txt` — allows `/`, disallows admin/dashboard/reset pages, points to sitemap.
  - Removed stale `<meta description="A product of emergent.sh">` from `public/index.html` so Helmet's dynamic tag wins.
- **P2 Sortable admin tables**: New `useSortableTable(rows, defaultKey, defaultDir, accessors)` hook + `<HeaderButton k="name" label="Nama" />`. Users tab table headers now clickable ASC↔DESC with visible arrow indicator. Numeric accessor for `referral_credit`.
- **P3 Auto-assign group on payment paid**:
  - New helper `auto_assign_group_for_sub(sub_id)` — invoked inside `extend_subscription_from_payment` when payment→paid.
  - Logic: pick first active group (`status ∈ {active, None}`) with open slot for sub.role by `created_at ASC`. If none, auto-create new group inheriting `default_host_slots`/`default_regular_slots` from service. New group carries `auto_created:true`.
  - Idempotent (checks `sub.group_id` before running).
  - Role promotion validation: `PATCH /admin/subscriptions/{id}` with `role:'host'` now rejects (400) if target group already has an active host from a different subscription.
- **P3 Unassigned users endpoint**: New `GET /api/admin/groups/unassigned-users?service_id=X` returns users NOT currently in any group for that service, with a `has_pending_sub` flag if they've already paid but await assignment. Used by the redesigned AssignModal.
- **P4 Groups UX**:
  - Redesigned Groups tab is now a service-grouped accordion (`groups-by-service`). Each service shows total slots utilization + per-service "Buat grup" button.
  - Capacity bars use traffic-light color (green <75%, yellow 75-99%, red 100%).
  - Group cards show `auto` badge when auto-created + inline member list with **promote/demote/remove** actions (`Crown` icon for host).
  - AssignModal fetches only unassigned candidates, shows real-time slot counts per role, disables role radio when its slots are full.
- **Testing**: 9/9 iter15 backend tests PASS + 100% frontend flows verified. One design bug (meta duplication) identified + fixed same iteration.

## Iteration 16 (2026-02-19) — Email Verification + SEO Root + More Sortable Tables
- **P0 Email verification for manual signup**:
  - `POST /auth/register` no longer auto-logins. Creates user with `email_verified:false`, `auth_provider:'manual'`, then generates a 24h SHA256-hashed token in `db.email_verifications` and emails a `/verify-email?token=...` link.
  - `POST /auth/verify-email` — validates token, marks user verified, sets auth cookie, and returns user+token for auto-login.
  - `POST /auth/resend-verification` — rate-limited 1 per email per 3 minutes. Uniform response (no `rate_limited:true` leak) to prevent email enumeration.
  - `POST /auth/login` blocks users with `auth_provider='manual'` AND `email_verified:false` (403). Legacy users without `auth_provider` field still pass through unchanged.
  - Google auth path auto-sets `email_verified:true` + `email_verified_at` on user upsert.
  - Frontend: new pages `/verify-email` (auto-verifies + auto-logins) and `/register-check-email?email=...` (post-signup "cek inbox" screen with 3-step guide + resend button). Registration flow no longer navigates to `/dashboard`; goes to check-email page.
- **P1 SEO discoverability at root**:
  - Static `frontend/public/robots.txt` — serves at `patungandigital.id/robots.txt`, points to `Sitemap: https://patungandigital.id/api/sitemap.xml`. Google Search Console accepts sitemap anywhere.
  - `SEO` component now injects `<meta name="google-site-verification">` when `REACT_APP_GSC_VERIFY` env var is set — one-line domain verification.
  - New setup guide: `/app/docs/google-search-console-guide.md` with 5-step verification + submit + tips + troubleshooting matrix.
- **P2 Sortable headers on more tabs**:
  - Payments tab: `sort-user`, `sort-service_name`, `sort-amount`, `sort-due_date`, `sort-status` — with numeric accessor for amount.
  - Subscriptions tab: `sort-user`, `sort-service`, `sort-price`, `sort-start`, `sort-status` — with nested accessors for `user.name` and `service.name`.
  - Users tab (from iter15) still has full sort coverage.
- **Testing**: 12/12 iter16 backend tests PASS + 100% frontend flows. 1 minor enumeration leak in `resend-verification` was identified by testing agent and fixed same iteration.

## Iteration 17 (2026-02-19) — Welcome Email post-verification
- **New helper** `_send_welcome_email(email, name, referral_code)` in `server.py` — sends branded HTML email (Bahasa Indonesia) via existing SendGrid pipeline.
- **Content**: Hero header (patungandigital.id branding), personalized greeting, 5-step "Cara Mulai Berlangganan" onboarding checklist, CTA button to Dashboard, referral code card (yellow highlight, monospace big code), WhatsApp share button (pre-filled message with referral link) + Copy Link button.
- **Trigger**: `POST /api/auth/verify-email` — after user is marked verified, endpoint ensures referral_code exists (auto-generates via `ensure_referral_code`), then sends welcome email (try/except so SendGrid failures don't block verify flow), then sets idempotency flags `welcome_email_sent=True` + `welcome_email_sent_at` (ISO string).
- **Testing**: 12/12 iter17 backend tests PASS. Manual curl end-to-end verified (test user welcome_test_1784446615@example.com received verified=True + welcome_email_sent=True + referral_code auto-generated).

## Iteration 18 (2026-02-19) — Bug fixes + Ikut Patungan flow
- **P0 FIX — Verify-email idempotent**: Endpoint `POST /api/auth/verify-email` now accepts token even if already used (as long as it belongs to a real user and not expired). Root cause: React StrictMode double-invoked useEffect + Gmail/corp email prefetchers caused the second POST to hit an already-consumed token → 400 error → user saw error page even though verification succeeded. Fixed backend (idempotent lookup) + frontend (useRef guard).
- **P6 NEW — Admin manual email verify**: New endpoint `POST /api/admin/users/{user_id}/verify-email` — bypasses token flow, marks user verified, invalidates pending tokens, sends welcome email idempotently. UI: green envelope button in Admin → Users tab, appears only for unverified non-admin users. New "Verified" column shows Ya/Belum status.
- **P1 NEW — Ikut Patungan self-service flow**: New endpoint `POST /api/me/subscriptions/join` accepts `{service_id, duration_months}`. Creates pending subscription (no group yet) + pending payment with correct amount = service.price_regular × months. Duplicate active/pending subs for same service blocked with 400. New `JoinModal` component in UserDashboard shows service picker + duration selector (1/3/6/12) + total price + confirmation → routes user to Payments tab to pick QRIS/Midtrans. Home CTA now routes logged-in users to `/dashboard?action=join`. Empty state in SubsPanel replaced with "Pilih Layanan" CTA.
- **P3 FIX — Onboarding step**: `first_payment` step relabeled from "Bayar tagihan pertama" → "Ikut patungan pertama (pilih layanan)". Done-check now considers any existing subscription. Onboarding CTA now opens JoinModal.
- **P4 NEW — Sort controls**: WaitlistTab uses `useSortableTable` for column headers (created_at, email, name, service, status). TestimonialsTab + AnnouncementsTab get "Sort by" dropdown (created_at, rating/severity, title, expires_at).
- **P5 NEW — Welcome email retry queue**: New async fn `_retry_pending_welcome_emails` runs on each scheduler tick (1h). Finds verified users where `welcome_email_sent!=True` and `welcome_email_retries<3`, retries send, increments counter, marks `welcome_email_given_up` after 3 failed attempts. Skips users verified < 5 min ago to avoid racing the main handler.

## Iteration 19 (2026-02-19) — Annual bonus + FRONTEND_URL fix + Referral tier rework + TTL index
- **P0 NEW — 12-month bonus (Bayar 11, Dapat 12)**: In `POST /me/subscriptions/join`, when `duration_months==12` the amount is discounted to `price × 11` (billable_months=11) while user still gets 12 months of access. Payment doc stores `annual_bonus_applied=True`, `original_amount`, `billable_months`. JoinModal shows: (a) top promo banner (red-orange gradient), (b) HEMAT badge on 12-month button, (c) summary with strikethrough original price + green "Hemat X · 1 bulan gratis" tag.
- **P1 FIX — FRONTEND_URL**: backend/.env was hardcoded to `http://localhost:3000`, causing email verification links to be un-clickable in production. Updated to `https://group-stream-admin.preview.emergentagent.com` in the preview env. **PRODUCTION deployment must set FRONTEND_URL to the production domain (e.g. `https://group-stream-admin.emergent.host`)** — user notified.
- **P3a NEW — Referral tier rework**: `TIER_THRESHOLDS` updated to Tier 1 = 10 refs → 1 mo, Tier 2 = 15 refs → 2 mo (cumulative 3 mo), Tier 3 = 45 refs → 5 mo (cumulative 8 mo). Home page tier chips + UserDashboard ReferralPanel automatically pick up new values from backend.
- **P3b NEW — TTL indexes**: Added `expireAfterSeconds=86400` indexes on `email_verifications.expires_at` and `password_resets.expires_at`. Documents auto-purge 1 day after expiry, keeping the collections lean without a cleanup cron.
- **P2 DEFERRED — Extract routers/auth.py**: Auth section (~350 lines) not extracted this iteration due to risk of breaking JWT/Google login flow. Will attempt in Iter 20 after adding a full auth backend test suite as a safety net.

## Backlog / next tasks
- **P2 (still open)**: Extract `routers/auth.py` — need full auth test suite as safety net first.
- **P3**: Object Storage for base64 media.
- **P3**: SendGrid fallback / dead-letter queue for failed verification emails (currently silent-fail).
- **P3**: Bounce-detection for invalid emails so unverified users don't accumulate.
- **P3**: Full-domain sitemap alias — serve at `/sitemap.xml` (root) via a build-time static file that mirrors `/api/sitemap.xml`. Requires a build hook or nginx rewrite.
- **P4 (from iter15)**: Expose `default_host_slots` / `default_regular_slots` in Service edit modal.







