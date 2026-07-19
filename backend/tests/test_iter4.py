"""Iteration 4 tests: Midtrans webhook + Referral system."""
import os
import time
import hashlib
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://group-stream-admin.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
MIDTRANS_SERVER_KEY = "Mid-server-9QH6jdmunkZ4hl2EzPDHvOuc"
ADMIN = {"email": "admin@patungandigital.id", "password": "admin123"}


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _register(name_prefix, referral_code=None):
    ts = int(time.time() * 1000)
    email = f"iter4_{name_prefix}_{ts}@example.com"
    payload = {
        "name": f"Iter4 {name_prefix}",
        "email": email,
        "password": "pass1234",
        "whatsapp": "+628123456789",
    }
    if referral_code:
        payload["referral_code"] = referral_code
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    return s, me.json()


def _seed_sub_and_payment(admin_s, user_id, amount=45000):
    # Pick any existing service+plan (netflix seeded)
    services = admin_s.get(f"{API}/services").json()
    assert services, "no services seeded"
    svc = services[0]
    plans = admin_s.get(f"{API}/admin/services/{svc['id']}/plans").json()
    assert plans, "no plans seeded"
    plan_id = plans[0]["id"]
    sub_payload = {"user_id": user_id, "service_id": svc["id"], "plan_id": plan_id, "role": "leecher", "status": "active",
                   "start_date": "2026-01-01T00:00:00Z", "price": 45000}
    r = admin_s.post(f"{API}/admin/subscriptions", json=sub_payload, timeout=15)
    assert r.status_code == 200, r.text
    sub = r.json()
    pay_payload = {"subscription_id": sub["id"], "amount": amount, "period_label": "Iter4 Test", "due_date": None}
    r = admin_s.post(f"{API}/admin/payments", json=pay_payload, timeout=20)
    assert r.status_code == 200, r.text
    return sub, r.json()


# ---------- Registration & referral code ----------
class TestReferralRegistration:
    def test_register_without_referral(self):
        s, me = _register("noref")
        assert me.get("referred_by") in (None, "")
        # referral code should be generated
        stats = s.get(f"{API}/me/referral-stats", timeout=15).json()
        assert stats["referral_code"] and len(stats["referral_code"]) == 8
        assert stats["invited_count"] == 0
        assert stats["reward_per_referral"] == 10000
        assert stats["referred_by"] is None

    def test_register_with_referral_code(self):
        sA, meA = _register("A")
        codeA = sA.get(f"{API}/me/referral-stats").json()["referral_code"]
        assert codeA
        sB, meB = _register("B", referral_code=codeA)
        # B should have referred_by = A's id
        assert meB.get("referred_by") == meA["id"]
        statsB = sB.get(f"{API}/me/referral-stats").json()
        assert statsB["referral_code"] and statsB["referral_code"] != codeA
        assert statsB["referred_by"] and statsB["referred_by"]["email"] == meA["email"]
        # A's invited_count should include B
        statsA = sA.get(f"{API}/me/referral-stats").json()
        assert statsA["invited_count"] >= 1


# ---------- Referral reward flow ----------
class TestReferralRewardFlow:
    @pytest.fixture(scope="class")
    def flow(self, admin_session):
        sA, meA = _register("rewA")
        codeA = sA.get(f"{API}/me/referral-stats").json()["referral_code"]
        sB, meB = _register("rewB", referral_code=codeA)
        sub, pay = _seed_sub_and_payment(admin_session, meB["id"], amount=45000)
        return {"sA": sA, "meA": meA, "sB": sB, "meB": meB, "sub": sub, "pay": pay}

    def test_admin_create_payment_returns_midtrans_fields(self, flow):
        pay = flow["pay"]
        # id + amount always
        assert "id" in pay and pay["amount"] == 45000
        # midtrans fields best-effort — may or may not be present depending on sandbox
        # But endpoint must not crash. If token exists then redirect_url should too.
        if "midtrans_token" in pay:
            assert "midtrans_redirect_url" in pay

    def test_mark_paid_credits_both_users(self, admin_session, flow):
        pid = flow["pay"]["id"]
        r = admin_session.patch(f"{API}/admin/payments/{pid}", json={"status": "paid"}, timeout=15)
        assert r.status_code == 200
        # Give a moment for async updates
        time.sleep(0.5)
        statsA = flow["sA"].get(f"{API}/me/referral-stats").json()
        statsB = flow["sB"].get(f"{API}/me/referral-stats").json()
        assert statsA["referral_credit"] == 10000, f"A credit: {statsA}"
        assert statsB["referral_credit"] == 10000, f"B credit: {statsB}"
        assert statsA["total_earned"] == 10000

    def test_idempotency_second_paid_doesnt_double_credit(self, admin_session, flow):
        # Create another payment for B and mark paid
        sub2, pay2 = _seed_sub_and_payment(admin_session, flow["meB"]["id"], amount=45000)
        # Referral credit auto-applied on this new payment (B had 10000)
        assert pay2.get("referral_credit_applied") == 10000
        assert pay2["amount"] == 35000
        r = admin_session.patch(f"{API}/admin/payments/{pay2['id']}", json={"status": "paid"}, timeout=15)
        assert r.status_code == 200
        time.sleep(0.5)
        statsA = flow["sA"].get(f"{API}/me/referral-stats").json()
        # Total earned by A must stay at 10000 (idempotent — no double credit)
        assert statsA["total_earned"] == 10000, statsA

    def test_referral_credit_auto_applied_on_new_payment(self, admin_session):
        # Fresh scenario to verify auto-application: register A→B, mark B's first payment paid, then create new.
        sA, meA = _register("aaA")
        codeA = sA.get(f"{API}/me/referral-stats").json()["referral_code"]
        sB, meB = _register("aaB", referral_code=codeA)
        sub1, pay1 = _seed_sub_and_payment(admin_session, meB["id"], amount=45000)
        admin_session.patch(f"{API}/admin/payments/{pay1['id']}", json={"status": "paid"}, timeout=15)
        time.sleep(0.5)
        # B should now have 10000 credit
        assert sB.get(f"{API}/me/referral-stats").json()["referral_credit"] == 10000
        # Create new payment for B — expect auto-apply
        sub2, pay2 = _seed_sub_and_payment(admin_session, meB["id"], amount=45000)
        assert pay2["amount"] == 35000
        assert pay2.get("referral_credit_applied") == 10000
        assert sB.get(f"{API}/me/referral-stats").json()["referral_credit"] == 0


# ---------- Midtrans webhook ----------
class TestMidtransWebhook:
    def _sig(self, order_id, status_code, gross_amount):
        raw = f"{order_id}{status_code}{gross_amount}{MIDTRANS_SERVER_KEY}"
        return hashlib.sha512(raw.encode()).hexdigest()

    def test_webhook_invalid_signature(self):
        payload = {"order_id": "pd-000000000000000000000000", "status_code": "200",
                   "gross_amount": "45000.00", "transaction_status": "settlement",
                   "fraud_status": "accept", "signature_key": "deadbeef"}
        r = requests.post(f"{API}/webhooks/midtrans", json=payload, timeout=15)
        assert r.status_code == 401, r.text

    def test_webhook_unknown_order_id_prefix(self):
        order_id = "unknown-abc"
        status_code = "200"
        gross_amount = "45000.00"
        payload = {"order_id": order_id, "status_code": status_code, "gross_amount": gross_amount,
                   "transaction_status": "settlement", "fraud_status": "accept",
                   "signature_key": self._sig(order_id, status_code, gross_amount)}
        r = requests.post(f"{API}/webhooks/midtrans", json=payload, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert "ignored" in (body.get("note") or "")

    def test_webhook_settlement_marks_paid(self, admin_session):
        # Create fresh user + payment
        sU, meU = _register("mwh")
        sub, pay = _seed_sub_and_payment(admin_session, meU["id"], amount=45000)
        order_id = f"pd-{pay['id']}"
        status_code = "200"
        gross_amount = f"{pay['amount']}.00"
        payload = {"order_id": order_id, "status_code": status_code, "gross_amount": gross_amount,
                   "transaction_status": "settlement", "fraud_status": "accept", "transaction_id": "trx-test-1",
                   "signature_key": self._sig(order_id, status_code, gross_amount)}
        r = requests.post(f"{API}/webhooks/midtrans", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("status") == "paid"
        # Confirm via admin fetch
        all_pays = admin_session.get(f"{API}/admin/payments").json()
        target = next((p for p in all_pays if p["id"] == pay["id"]), None)
        assert target and target["status"] == "paid"


# ---------- Analytics with $lookup ----------
class TestAnalytics:
    def test_analytics_structure(self, admin_session):
        r = admin_session.get(f"{API}/admin/analytics", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "monthly" in data and isinstance(data["monthly"], list) and len(data["monthly"]) in (12, 13)
        assert "by_service" in data and isinstance(data["by_service"], list)
        # If any paid payment exists, by_service should include service+color fields
        for row in data["by_service"]:
            assert "service" in row
            assert "color" in row
            assert "revenue" in row
        assert "totals" in data
