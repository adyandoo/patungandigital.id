"""Iter12 tests: payment duration + subscription auto-extend + password reset + TZ + payments filter."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dateutil.relativedelta import relativedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@patungandigital.id"
ADMIN_PW = "Adm!nPd-JavpOaidEa6wZgFnBS"
RUN_ID = f"iter12{uuid.uuid4().hex[:6]}"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def service_id(admin):
    r = admin.get(f"{BASE_URL}/api/services")
    assert r.status_code == 200
    svcs = r.json()
    assert svcs, "need at least 1 service"
    return svcs[0]["id"]


def _make_user(admin, tag):
    email = f"{RUN_ID}{tag}_{uuid.uuid4().hex[:6]}@example.com"
    r = admin.post(f"{BASE_URL}/api/admin/users", json={
        "email": email, "password": "userpass123", "name": f"Iter12 {tag}", "role": "user",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"], email


def _make_sub(admin, user_id, service_id, price=45000):
    r = admin.post(f"{BASE_URL}/api/admin/subscriptions", json={
        "user_id": user_id,
        "service_id": service_id,
        "role": "regular",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "price": price,
        "status": "active",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin):
    yield
    admin.post(f"{BASE_URL}/api/admin/cleanup-test-users", params={"prefix": RUN_ID})


# ---------- P0 DURATION ----------
class TestDuration:
    def test_create_payment_with_duration(self, admin, service_id):
        uid, _ = _make_user(admin, "dur1")
        sub_id = _make_sub(admin, uid, service_id, price=45000)
        r = admin.post(f"{BASE_URL}/api/admin/payments", json={
            "subscription_id": sub_id, "amount": 45000, "duration_months": 3,
        })
        assert r.status_code in (200, 201), r.text
        p = r.json()
        assert p["duration_months"] == 3
        assert p["base_amount"] == 45000
        assert p["payment_method"] is None
        assert p["status"] == "pending"

    def test_mark_paid_extends_sub_and_revert(self, admin, service_id):
        uid, _ = _make_user(admin, "dur2")
        sub_id = _make_sub(admin, uid, service_id)
        r = admin.post(f"{BASE_URL}/api/admin/payments", json={
            "subscription_id": sub_id, "amount": 45000, "duration_months": 3,
        })
        pay_id = r.json()["id"]
        before = datetime.now(timezone.utc)
        # Mark paid
        r = admin.patch(f"{BASE_URL}/api/admin/payments/{pay_id}", json={"status": "paid"})
        assert r.status_code == 200, r.text
        # Fetch sub
        subs = admin.get(f"{BASE_URL}/api/admin/subscriptions").json()
        sub = next(s for s in subs if s["id"] == sub_id)
        assert sub["status"] == "active"
        start = datetime.fromisoformat(sub["start_date"])
        end = datetime.fromisoformat(sub["end_date"])
        expected_end = start + relativedelta(months=3)
        delta = abs((end - expected_end).total_seconds())
        assert delta < 60, f"end {end} vs expected {expected_end}"

        # Revert: paid -> overdue rolls back
        r = admin.patch(f"{BASE_URL}/api/admin/payments/{pay_id}", json={"status": "overdue"})
        assert r.status_code == 200
        subs = admin.get(f"{BASE_URL}/api/admin/subscriptions").json()
        sub2 = next(s for s in subs if s["id"] == sub_id)
        end2 = datetime.fromisoformat(sub2["end_date"])
        rolled = end - relativedelta(months=3)
        assert abs((end2 - rolled).total_seconds()) < 60

        # Re-mark paid: should extend again by 3 months
        r = admin.patch(f"{BASE_URL}/api/admin/payments/{pay_id}", json={"status": "paid"})
        assert r.status_code == 200
        subs = admin.get(f"{BASE_URL}/api/admin/subscriptions").json()
        sub3 = next(s for s in subs if s["id"] == sub_id)
        end3 = datetime.fromisoformat(sub3["end_date"])
        assert abs((end3 - end).total_seconds()) < 60, f"re-mark: end3 {end3} vs expected {end}"

    def test_upload_receipt_extends_by_duration(self, admin, service_id):
        uid, email = _make_user(admin, "dur3")
        # Login as user
        us = requests.Session()
        rl = us.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "userpass123"})
        assert rl.status_code == 200
        sub_id = _make_sub(admin, uid, service_id)
        r = admin.post(f"{BASE_URL}/api/admin/payments", json={
            "subscription_id": sub_id, "amount": 45000, "duration_months": 2,
        })
        pay_id = r.json()["id"]
        rr = us.post(f"{BASE_URL}/api/me/payments/{pay_id}/receipt", json={
            "payment_id": pay_id,
            "file_base64": "data:image/png;base64,iVBORw0KGgo=",
            "file_name": "r.png",
        })
        assert rr.status_code == 200, rr.text
        assert rr.json()["status"] == "paid"
        sub = next(s for s in admin.get(f"{BASE_URL}/api/admin/subscriptions").json() if s["id"] == sub_id)
        start = datetime.fromisoformat(sub["start_date"])
        end = datetime.fromisoformat(sub["end_date"])
        expected = start + relativedelta(months=2)
        assert abs((end - expected).total_seconds()) < 60

    def test_second_payment_extends_from_prior_end(self, admin, service_id):
        uid, _ = _make_user(admin, "dur4")
        sub_id = _make_sub(admin, uid, service_id)
        p1 = admin.post(f"{BASE_URL}/api/admin/payments", json={
            "subscription_id": sub_id, "amount": 45000, "duration_months": 3,
        }).json()
        admin.patch(f"{BASE_URL}/api/admin/payments/{p1['id']}", json={"status": "paid"})
        end1 = datetime.fromisoformat(next(
            s for s in admin.get(f"{BASE_URL}/api/admin/subscriptions").json() if s["id"] == sub_id
        )["end_date"])
        # Second payment
        p2 = admin.post(f"{BASE_URL}/api/admin/payments", json={
            "subscription_id": sub_id, "amount": 45000, "duration_months": 1,
        }).json()
        admin.patch(f"{BASE_URL}/api/admin/payments/{p2['id']}", json={"status": "paid"})
        end2 = datetime.fromisoformat(next(
            s for s in admin.get(f"{BASE_URL}/api/admin/subscriptions").json() if s["id"] == sub_id
        )["end_date"])
        expected = end1 + relativedelta(months=1)
        assert abs((end2 - expected).total_seconds()) < 60, f"end2={end2} expected={expected}"


# ---------- P0 PASSWORD RESET ----------
class TestPasswordReset:
    def test_forgot_existing_and_nonexistent(self, admin):
        uid, email = _make_user(admin, "pw1")
        r1 = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": email})
        assert r1.status_code == 200
        r2 = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": "no-such-user-xxx@example.com"})
        assert r2.status_code == 200

    def test_reset_password_with_valid_token_flow(self, admin):
        # Since we can't easily obtain the raw token from email, we insert token via a helper: create user, then create a token via direct API by triggering forgot then querying db is not possible from HTTP.
        # We test the negative cases only from HTTP: invalid token → 400.
        r = requests.post(f"{BASE_URL}/api/auth/reset-password", json={"token": "invalid-token-xyz", "new_password": "newpass123"})
        assert r.status_code == 400

    def test_reset_password_short_pw_422(self, admin):
        r = requests.post(f"{BASE_URL}/api/auth/reset-password", json={"token": "anything", "new_password": "abc"})
        assert r.status_code == 422

    def test_admin_reset_user_password(self, admin):
        uid, email = _make_user(admin, "pw2")
        r = admin.post(f"{BASE_URL}/api/admin/users/{uid}/reset-password", json={"notify_email": False})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "default_password" in data
        default_pw = data["default_password"]
        # Login with new default
        s = requests.Session()
        r2 = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": default_pw})
        assert r2.status_code == 200

    def test_admin_reset_non_admin_forbidden(self, admin):
        uid, email = _make_user(admin, "pw3")
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "userpass123"})
        r = s.post(f"{BASE_URL}/api/admin/users/{uid}/reset-password", json={"notify_email": False})
        assert r.status_code in (401, 403)


# ---------- P1 REFACTOR ----------
class TestRefactorEndpoints:
    def test_payment_config_public(self, admin):
        r = requests.get(f"{BASE_URL}/api/payment-config")
        assert r.status_code == 200

    def test_admin_payment_config_get_put(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/payment-config")
        assert r.status_code == 200
        r2 = admin.put(f"{BASE_URL}/api/admin/payment-config", json={
            "qris_notes": "iter12", "midtrans_fee_percent": 5.0, "manual_bank_info": "",
        })
        assert r2.status_code == 200

    def test_admin_invoice_config_get_put(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/invoice-config")
        assert r.status_code == 200
        r2 = admin.put(f"{BASE_URL}/api/admin/invoice-config", json={
            "day_of_month": 1, "due_days": 7, "enabled": True,
        })
        assert r2.status_code == 200

    def test_admin_general_config_get_put(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/general-config")
        assert r.status_code == 200
        r2 = admin.put(f"{BASE_URL}/api/admin/general-config", json={
            "default_new_user_password": "patungan123",
        })
        assert r2.status_code == 200

    def test_users_template_csv(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/users/template.csv")
        assert r.status_code == 200
        assert "email" in r.text.lower()


# ---------- P2 TIMEZONE / SCHEDULER ----------
class TestTimezone:
    def test_force_generate_now_sets_tz_and_period(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/invoices/generate-now")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("timezone") == "Asia/Jakarta"
        assert "period" in data
        # Now verify last_run_period_label recorded via config (indirectly, we can't query db directly via API — check by calling with force again returning same period)
        r2 = admin.post(f"{BASE_URL}/api/admin/invoices/generate-now")
        assert r2.status_code == 200
        assert r2.json()["period"] == data["period"]


# ---------- P3 PAYMENTS FILTER ----------
class TestPaymentsFilter:
    def test_filter_all_auto_manual(self, admin, service_id):
        uid, _ = _make_user(admin, "flt")
        sub_id = _make_sub(admin, uid, service_id)
        # create a manual payment
        pm = admin.post(f"{BASE_URL}/api/admin/payments", json={
            "subscription_id": sub_id, "amount": 15000, "duration_months": 1,
        }).json()
        # trigger auto-generation
        admin.post(f"{BASE_URL}/api/admin/invoices/generate-now")

        all_r = admin.get(f"{BASE_URL}/api/admin/payments").json()
        auto_r = admin.get(f"{BASE_URL}/api/admin/payments", params={"auto_generated": "true"}).json()
        manual_r = admin.get(f"{BASE_URL}/api/admin/payments", params={"auto_generated": "false"}).json()
        assert len(all_r) >= len(auto_r)
        assert len(all_r) >= len(manual_r)
        assert all(p.get("auto_generated") is True for p in auto_r)
        assert all(not p.get("auto_generated") for p in manual_r)
        # manual payment should be in manual list
        assert any(p["id"] == pm["id"] for p in manual_r)
