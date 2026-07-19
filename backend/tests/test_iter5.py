"""Iteration 5 tests: Tier reward system + Public Leaderboard + free_months_credit consumption."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@patungandigital.id", "password": "admin123"}


# ---------- Fixtures / helpers ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _register(name_prefix, referral_code=None):
    ts = int(time.time() * 1000)
    email = f"iter5_{name_prefix}_{ts}@example.com"
    payload = {
        "name": f"Iter5 {name_prefix}",
        "email": email,
        "password": "pass1234",
        "whatsapp": "+628123456789",
    }
    if referral_code:
        payload["referral_code"] = referral_code
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me", timeout=15).json()
    return s, me


def _seed_sub_and_payment(admin_s, user_id, amount=45000):
    services = admin_s.get(f"{API}/services").json()
    svc = services[0]
    plans = admin_s.get(f"{API}/admin/services/{svc['id']}/plans").json()
    plan_id = plans[0]["id"]
    sub_payload = {"user_id": user_id, "service_id": svc["id"], "plan_id": plan_id, "role": "leecher",
                   "status": "active", "start_date": "2026-01-01T00:00:00Z", "price": 45000}
    r = admin_s.post(f"{API}/admin/subscriptions", json=sub_payload, timeout=15)
    assert r.status_code == 200, r.text
    sub = r.json()
    pay_payload = {"subscription_id": sub["id"], "amount": amount, "period_label": "Iter5 Test", "due_date": None}
    r = admin_s.post(f"{API}/admin/payments", json=pay_payload, timeout=25)
    assert r.status_code == 200, r.text
    return sub, r.json()


def _register_and_pay(admin_s, referrer_code, prefix):
    """Register a new user referred by code and mark first payment paid."""
    sU, meU = _register(prefix, referral_code=referrer_code)
    _, pay = _seed_sub_and_payment(admin_s, meU["id"], amount=45000)
    r = admin_s.patch(f"{API}/admin/payments/{pay['id']}", json={"status": "paid"}, timeout=15)
    assert r.status_code == 200
    return sU, meU


# ---------- Public leaderboard ----------
class TestLeaderboardPublic:
    def test_leaderboard_shape_no_auth(self):
        r = requests.get(f"{API}/leaderboard", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) >= {"monthly", "all_time", "month_label"}
        assert isinstance(data["monthly"], list)
        assert isinstance(data["all_time"], list)
        assert isinstance(data["month_label"], str) and len(data["month_label"]) > 3

    def test_leaderboard_row_shape_and_ranks(self):
        r = requests.get(f"{API}/leaderboard", timeout=15)
        data = r.json()
        # Combined rows: at least one is expected because iter4 has successful referrals
        all_rows = data["all_time"]
        assert len(all_rows) >= 1, "expected at least 1 all_time leaderboard entry from iter4 referrals"
        for i, row in enumerate(all_rows):
            assert row["rank"] == i + 1
            for k in ("user_id", "name", "initials", "count", "total_earned", "tiers_granted"):
                assert k in row
        # sorted desc by count
        counts = [row["count"] for row in all_rows]
        assert counts == sorted(counts, reverse=True)


# ---------- Referral stats extended fields ----------
class TestReferralStatsExtended:
    def test_stats_include_new_fields(self):
        s, _ = _register("statsuser")
        stats = s.get(f"{API}/me/referral-stats", timeout=15).json()
        for k in ("free_months_credit", "successful_count", "tiers", "tiers_granted", "next_tier"):
            assert k in stats, f"missing key: {k} in {stats}"
        assert stats["free_months_credit"] == 0
        assert stats["successful_count"] == 0
        assert isinstance(stats["tiers"], list) and len(stats["tiers"]) == 3
        tiers_nums = [t["tier"] for t in stats["tiers"]]
        assert tiers_nums == [1, 2, 3]
        assert stats["tiers_granted"] == []
        assert stats["next_tier"] and stats["next_tier"]["tier"] == 1


# ---------- Tier 1 (5 referrals) grant + idempotency ----------
class TestTier1Grant:
    @pytest.fixture(scope="class")
    def refr(self, admin_session):
        sR, meR = _register("t1_R")
        codeR = sR.get(f"{API}/me/referral-stats").json()["referral_code"]
        # Register + pay for 5 downstream users
        for i in range(5):
            _register_and_pay(admin_session, codeR, f"t1_b{i}")
            time.sleep(0.15)
        return {"sR": sR, "meR": meR, "codeR": codeR}

    def test_tier1_granted_after_5(self, refr):
        stats = refr["sR"].get(f"{API}/me/referral-stats").json()
        assert stats["successful_count"] >= 5
        assert 1 in stats["tiers_granted"], stats
        assert stats["free_months_credit"] >= 1

    def test_referral_reward_row_tier1_created(self, admin_session, refr):
        # No public endpoint — verify via leaderboard tier column
        lb = requests.get(f"{API}/leaderboard").json()
        # Find R in all_time
        target = next((r for r in lb["all_time"] if r["user_id"] == refr["meR"]["id"]), None)
        assert target is not None, "referrer R not on leaderboard"
        assert 1 in target["tiers_granted"]

    def test_maybe_grant_tier_is_idempotent(self, admin_session, refr):
        # Marking any prior paid payment again shouldn't double-add. We simulate by re-calling
        # apply via patch on an already-paid payment (should no-op due to first_paid_at).
        # Simply verify free_months_credit didn't accidentally double after previous test.
        stats = refr["sR"].get(f"{API}/me/referral-stats").json()
        # After tier1 (before free-month consumption): expect exactly 1 free month credit
        # (unless consumed later; captured baseline stored on the fixture obj)
        refr["free_before"] = stats["free_months_credit"]
        assert refr["free_before"] == 1  # crucial invariant


# ---------- free_months_credit consumption in admin_create_payment ----------
class TestFreeMonthConsumption:
    def test_free_month_consumed_amount_zero(self, admin_session):
        # Fresh R with 5 successful referrals -> free_months_credit=1
        sR, meR = _register("fm_R")
        codeR = sR.get(f"{API}/me/referral-stats").json()["referral_code"]
        for i in range(5):
            _register_and_pay(admin_session, codeR, f"fm_b{i}")
            time.sleep(0.1)
        stats = sR.get(f"{API}/me/referral-stats").json()
        assert stats["free_months_credit"] == 1
        # R also has referral_credit from being a referrer (10000 * 5 = 50000)
        assert stats["referral_credit"] >= 10000

        # Now create a payment FOR R — expect amount=0, free_month_applied=True
        _, pay = _seed_sub_and_payment(admin_session, meR["id"], amount=45000)
        assert pay["amount"] == 0, pay
        assert pay.get("free_month_applied") is True
        # referral_credit_applied should NOT be applied when free month used
        assert not pay.get("referral_credit_applied")

        # Verify user's free_months_credit decremented
        stats2 = sR.get(f"{API}/me/referral-stats").json()
        assert stats2["free_months_credit"] == 0
        # referral_credit unchanged (not consumed)
        assert stats2["referral_credit"] == stats["referral_credit"]


# ---------- Tier 2 (10 referrals) ----------
class TestTier2Grant:
    def test_tier2_after_10(self, admin_session):
        sR, meR = _register("t2_R")
        codeR = sR.get(f"{API}/me/referral-stats").json()["referral_code"]
        # 10 successful referrals
        for i in range(10):
            _register_and_pay(admin_session, codeR, f"t2_b{i}")
            time.sleep(0.1)
        stats = sR.get(f"{API}/me/referral-stats").json()
        assert stats["successful_count"] >= 10
        assert set(stats["tiers_granted"]) >= {1, 2}, stats
        # tier1=1 + tier2=2 = 3 free months (cumulative)
        assert stats["free_months_credit"] == 3, stats
        # Next tier should be 3
        assert stats["next_tier"] and stats["next_tier"]["tier"] == 3


# ---------- Existing referral cash flow still works ----------
class TestExistingReferralUnaffected:
    def test_cash_credit_flow_still_works(self, admin_session):
        sA, meA = _register("ex_A")
        codeA = sA.get(f"{API}/me/referral-stats").json()["referral_code"]
        sB, meB = _register("ex_B", referral_code=codeA)
        _, payB = _seed_sub_and_payment(admin_session, meB["id"], amount=45000)
        admin_session.patch(f"{API}/admin/payments/{payB['id']}", json={"status": "paid"}, timeout=15)
        time.sleep(0.4)
        statsA = sA.get(f"{API}/me/referral-stats").json()
        statsB = sB.get(f"{API}/me/referral-stats").json()
        assert statsA["referral_credit"] >= 10000
        assert statsB["referral_credit"] == 10000
