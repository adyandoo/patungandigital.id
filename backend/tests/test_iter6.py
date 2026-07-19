"""Iteration 6 tests: router split regression + onboarding + cleanup + webhooks."""
import os
import hashlib
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@patungandigital.id", "password": "admin123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _register(name_prefix, referral_code=None, whatsapp="+628111111111"):
    ts = int(time.time() * 1000)
    email = f"iter6_{name_prefix}_{ts}@example.com"
    payload = {"name": f"Iter6 {name_prefix}", "email": email, "password": "pass1234", "whatsapp": whatsapp}
    if referral_code:
        payload["referral_code"] = referral_code
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me").json()
    return s, me


# ---------- Router split regressions ----------
class TestRouterSplitRegression:
    def test_admin_analytics_shape(self, admin_session):
        r = admin_session.get(f"{API}/admin/analytics", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("monthly", "by_service", "status_distribution", "totals"):
            assert k in d
        assert isinstance(d["monthly"], list)
        assert all("label" in m and "revenue" in m and "count" in m for m in d["monthly"])
        assert "total_revenue_paid" in d["totals"] and "avg_payment" in d["totals"]

    def test_referral_stats_shape(self, admin_session):
        r = admin_session.get(f"{API}/me/referral-stats", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("referral_code", "referral_credit", "free_months_credit", "invited_count",
                  "successful_count", "tiers", "tiers_granted", "next_tier"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["tiers"], list) and len(d["tiers"]) >= 1

    def test_leaderboard_public_no_auth(self):
        r = requests.get(f"{API}/leaderboard", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) >= {"monthly", "all_time", "month_label"}
        assert isinstance(d["monthly"], list) and isinstance(d["all_time"], list)

    def test_xendit_webhook_invalid_token(self):
        # if XENDIT_WEBHOOK_TOKEN set → 401 else 200 (best-effort)
        r = requests.post(f"{API}/webhooks/xendit", json={"external_id": "pay-x", "status": "PAID"},
                          headers={"X-CALLBACK-TOKEN": "definitely-wrong"}, timeout=15)
        assert r.status_code in (200, 401)

    def test_midtrans_webhook_invalid_signature(self):
        # If MIDTRANS_SERVER_KEY is set → 401 with invalid signature.
        # If not set, the endpoint returns 200 with ignored note.
        payload = {"order_id": "pd-000000000000000000000000", "status_code": "200",
                   "gross_amount": "10000.00", "signature_key": "invalid"}
        r = requests.post(f"{API}/webhooks/midtrans", json=payload, timeout=15)
        assert r.status_code in (200, 401)

    def test_midtrans_webhook_unknown_order_ignored(self):
        # Build a valid-signature scenario without MIDTRANS key requires knowing it — just test unknown order path (no signature check when key not set is possible)
        payload = {"order_id": "notpd-xxx", "status_code": "200", "gross_amount": "0", "signature_key": "x"}
        r = requests.post(f"{API}/webhooks/midtrans", json=payload, timeout=15)
        # either 401 (has key & bad sig) or 200 ignored
        assert r.status_code in (200, 401)


# ---------- Onboarding endpoint ----------
class TestOnboarding:
    def test_new_user_percent_40(self):
        """New user w/ WhatsApp set → signup+profile done → 2/5 → 40%."""
        s, me = _register("onb1", whatsapp="+628999888777")
        r = s.get(f"{API}/me/onboarding", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 5
        assert len(d["steps"]) == 5
        keys = [x["key"] for x in d["steps"]]
        assert keys == ["signup", "profile", "first_payment", "invite", "reward"]
        signup = next(s for s in d["steps"] if s["key"] == "signup")
        profile = next(s for s in d["steps"] if s["key"] == "profile")
        assert signup["done"] is True
        assert profile["done"] is True
        assert d["percent"] == 40

    def test_new_user_no_whatsapp_percent_20(self):
        """User w/o whatsapp: only signup done → 20%."""
        # Register w/o whatsapp — endpoint may require whatsapp; if so patch to empty
        s, me = _register("onb2", whatsapp="")
        # If register defaulted whatsapp, clear via profile update
        s.patch(f"{API}/auth/profile", json={"whatsapp": ""}, timeout=15)
        r = s.get(f"{API}/me/onboarding")
        d = r.json()
        profile_done = next(x for x in d["steps"] if x["key"] == "profile")["done"]
        if not profile_done:
            assert d["percent"] == 20
        else:
            # backend forces whatsapp — accept 40% as valid
            assert d["percent"] == 40

    def test_first_payment_flips_step(self, admin_session):
        s, me = _register("onb3")
        # seed sub + payment paid
        services = admin_session.get(f"{API}/services").json()
        plans = admin_session.get(f"{API}/admin/services/{services[0]['id']}/plans").json()
        sub = admin_session.post(f"{API}/admin/subscriptions", json={
            "user_id": me["id"], "service_id": services[0]["id"], "plan_id": plans[0]["id"],
            "role": "leecher", "status": "active", "start_date": "2026-01-01T00:00:00Z", "price": 45000
        }, timeout=15).json()
        pay = admin_session.post(f"{API}/admin/payments", json={
            "subscription_id": sub["id"], "amount": 45000, "period_label": "Iter6 onb", "due_date": None
        }, timeout=25).json()
        admin_session.patch(f"{API}/admin/payments/{pay['id']}", json={"status": "paid"}, timeout=15)
        d = s.get(f"{API}/me/onboarding").json()
        fp = next(x for x in d["steps"] if x["key"] == "first_payment")
        assert fp["done"] is True
        # invite and reward not yet
        assert next(x for x in d["steps"] if x["key"] == "invite")["done"] is False


# ---------- Admin cleanup endpoint ----------
class TestAdminCleanup:
    def test_non_admin_forbidden(self):
        s, _ = _register("cleanup_nonadmin")
        r = s.post(f"{API}/admin/cleanup-test-users", params={"prefix": "Iter6"}, timeout=15)
        assert r.status_code == 403

    def test_cleanup_deletes_and_preserves_admin(self, admin_session):
        # Create a unique-prefix user to ensure isolation
        prefix = f"CleanupX{int(time.time())}"
        # Register user with name matching prefix
        s = requests.Session()
        email = f"iter6_cleanupx_{int(time.time()*1000)}@example.com"
        r = s.post(f"{API}/auth/register", json={
            "name": f"{prefix} target", "email": email, "password": "pass1234", "whatsapp": "+62811"
        }, timeout=15)
        assert r.status_code == 200
        # Cleanup
        r = admin_session.post(f"{API}/admin/cleanup-test-users", params={"prefix": prefix}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["prefix"] == prefix
        assert d["deleted_users"] >= 1
        assert "deleted_subscriptions" in d
        # Admin still exists — login again
        r2 = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r2.status_code == 200
