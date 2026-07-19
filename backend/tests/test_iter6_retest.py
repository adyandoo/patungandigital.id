"""Iter6 retest: verify bug fixes for
- organic (non-referred) user gets first_paid_at set + onboarding flips
- referred user: both users credited + admin log entry
- idempotency: second paid payment does NOT re-grant referral rewards
"""
import os
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
    assert r.status_code == 200
    return s


def _register(prefix, referral_code=None):
    ts = int(time.time() * 1000)
    email = f"iter6r_{prefix}_{ts}@example.com"
    payload = {"name": f"Iter6R {prefix}", "email": email, "password": "pass1234", "whatsapp": "+628111222333"}
    if referral_code:
        payload["referral_code"] = referral_code
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me").json()
    return s, me


def _create_paid_payment(admin_session, user_id, amount=45000, label="Retest"):
    services = admin_session.get(f"{API}/services").json()
    plans = admin_session.get(f"{API}/admin/services/{services[0]['id']}/plans").json()
    sub = admin_session.post(f"{API}/admin/subscriptions", json={
        "user_id": user_id, "service_id": services[0]["id"], "plan_id": plans[0]["id"],
        "role": "leecher", "status": "active", "start_date": "2026-01-01T00:00:00Z", "price": amount
    }, timeout=15).json()
    pay = admin_session.post(f"{API}/admin/payments", json={
        "subscription_id": sub["id"], "amount": amount, "period_label": label, "due_date": None
    }, timeout=25).json()
    r = admin_session.patch(f"{API}/admin/payments/{pay['id']}", json={"status": "paid"}, timeout=15)
    assert r.status_code == 200, r.text
    return sub, pay


class TestOrganicFirstPayment:
    def test_organic_user_first_payment_flips(self, admin_session):
        s, me = _register("organic")
        _create_paid_payment(admin_session, me["id"])
        d = s.get(f"{API}/me/onboarding").json()
        fp = next(x for x in d["steps"] if x["key"] == "first_payment")
        assert fp["done"] is True, f"first_payment.done should be True: {d}"
        assert d["percent"] >= 40


class TestReferralRewards:
    def test_referred_user_credits_both(self, admin_session):
        # 1. Register referrer
        s_ref, referrer = _register("referrer")
        stats = s_ref.get(f"{API}/me/referral-stats").json()
        ref_code = stats["referral_code"]
        assert ref_code
        # 2. Register referred user with the code
        s_new, new_user = _register("referred", referral_code=ref_code)
        # 3. Admin marks first payment as paid for the referred user
        _create_paid_payment(admin_session, new_user["id"])
        # 4. Referred user should have credit >= 10000 and first_paid_at set (via onboarding)
        rs = s_new.get(f"{API}/me/referral-stats").json()
        assert rs["referral_credit"] >= 10000, f"referred user credit: {rs}"
        # onboarding step first_payment done
        ob_new = s_new.get(f"{API}/me/onboarding").json()
        assert next(x for x in ob_new["steps"] if x["key"] == "first_payment")["done"] is True
        # 5. Referrer credit incremented and successful_count>=1
        rs2 = s_ref.get(f"{API}/me/referral-stats").json()
        assert rs2["referral_credit"] >= 10000, f"referrer credit: {rs2}"
        assert rs2["successful_count"] >= 1
        # 6. Admin activity log contains referral_reward_credited
        logs = admin_session.get(f"{API}/admin/logs", params={"limit": 200}, timeout=15)
        assert logs.status_code == 200, logs.text
        entries = logs.json()
        # entries may be list or {items:[...]}
        items = entries if isinstance(entries, list) else entries.get("items", entries.get("logs", []))
        found = any(e.get("action") == "referral_reward_credited" and str(new_user["id"]) in str(e) for e in items)
        assert found, f"referral_reward_credited log not found for user {new_user['id']}"

    def test_second_payment_is_idempotent(self, admin_session):
        # Register referrer + referred, pay once, get baseline credits, pay AGAIN, credits unchanged
        s_ref, referrer = _register("referrer2")
        ref_code = s_ref.get(f"{API}/me/referral-stats").json()["referral_code"]
        s_new, new_user = _register("referred2", referral_code=ref_code)
        _create_paid_payment(admin_session, new_user["id"], label="First")
        credit_ref_1 = s_ref.get(f"{API}/me/referral-stats").json()["referral_credit"]
        successful_1 = s_ref.get(f"{API}/me/referral-stats").json()["successful_count"]
        # Count referral_reward_credited log entries for this user
        logs_1 = admin_session.get(f"{API}/admin/logs", params={"limit": 500}, timeout=15).json()
        items_1 = logs_1 if isinstance(logs_1, list) else logs_1.get("items", logs_1.get("logs", []))
        count_1 = sum(1 for e in items_1 if e.get("action") == "referral_reward_credited" and str(new_user["id"]) in str(e))
        # Second paid payment for the same user
        _create_paid_payment(admin_session, new_user["id"], label="Second")
        credit_ref_2 = s_ref.get(f"{API}/me/referral-stats").json()["referral_credit"]
        successful_2 = s_ref.get(f"{API}/me/referral-stats").json()["successful_count"]
        logs_2 = admin_session.get(f"{API}/admin/logs", params={"limit": 500}, timeout=15).json()
        items_2 = logs_2 if isinstance(logs_2, list) else logs_2.get("items", logs_2.get("logs", []))
        count_2 = sum(1 for e in items_2 if e.get("action") == "referral_reward_credited" and str(new_user["id"]) in str(e))
        assert credit_ref_2 == credit_ref_1, f"referrer credit changed on 2nd payment: {credit_ref_1}->{credit_ref_2}"
        assert successful_2 == successful_1, "successful_count should not increment on 2nd paid payment"
        assert count_2 == count_1, f"referral_reward_credited log count should not increment: {count_1}->{count_2}"
