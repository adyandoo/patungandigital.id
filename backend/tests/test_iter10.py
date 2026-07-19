"""Iteration 10: Payment Config, Choose Method, Create Admin, Partial Sub Update, Orphan cleanup"""
import os
import time
import base64
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@patungandigital.id"
ADMIN_PASSWORD = "Adm!nPd-JavpOaidEa6wZgFnBS"

TS = str(int(time.time()))
UEMAIL = f"iter10_user_{TS}@example.com"
UPASS = "userpass1234"


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_ctx():
    r = requests.post(f"{API}/auth/register", json={
        "email": UEMAIL, "password": UPASS, "name": f"Iter10 User {TS}",
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def service_and_sub(admin_tok, user_ctx):
    # Reuse an existing service if there is one
    r = requests.get(f"{API}/services")
    assert r.status_code == 200
    services = r.json()
    assert services, "No services seeded"
    svc = services[0]
    # Create subscription for the user via admin
    payload = {
        "user_id": user_ctx["user"]["id"],
        "service_id": svc["id"],
        "plan_id": None,
        "group_id": None,
        "role": "member",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "price": 45000,
        "status": "active",
    }
    r = requests.post(f"{API}/admin/subscriptions", json=payload, headers=H(admin_tok))
    assert r.status_code == 200, r.text
    sub = r.json()
    return {"service": svc, "sub": sub}


# ---------------- (a) Payment Config ---------------- #
class TestPaymentConfig:
    def test_public_get_defaults(self):
        r = requests.get(f"{API}/payment-config")
        assert r.status_code == 200
        d = r.json()
        assert "qris_image_base64" in d
        assert "qris_notes" in d
        assert "manual_bank_info" in d
        assert "midtrans_fee_percent" in d
        assert isinstance(d["midtrans_fee_percent"], (int, float))

    def test_admin_get(self, admin_tok):
        r = requests.get(f"{API}/admin/payment-config", headers=H(admin_tok))
        assert r.status_code == 200

    def test_user_cannot_put(self, user_ctx):
        r = requests.put(f"{API}/admin/payment-config",
                         json={"midtrans_fee_percent": 7}, headers=H(user_ctx["token"]))
        assert r.status_code == 403

    def test_admin_put_updates(self, admin_tok):
        img_b64 = "data:image/png;base64," + base64.b64encode(b"\x89PNG_TESTIMG").decode()
        payload = {
            "qris_image_base64": img_b64,
            "qris_notes": "TEST_QRIS notes",
            "midtrans_fee_percent": 5,
            "manual_bank_info": "TEST_BANK BCA 12345",
        }
        r = requests.put(f"{API}/admin/payment-config", json=payload, headers=H(admin_tok))
        assert r.status_code == 200, r.text
        # Verify persistence via public GET
        r = requests.get(f"{API}/payment-config")
        d = r.json()
        assert d["qris_image_base64"] == img_b64
        assert d["qris_notes"] == "TEST_QRIS notes"
        assert d["manual_bank_info"] == "TEST_BANK BCA 12345"
        assert float(d["midtrans_fee_percent"]) == 5.0


# ---------------- (c) Admin Create Admin ---------------- #
class TestCreateAdmin:
    def test_weak_password_rejected(self, admin_tok):
        r = requests.post(f"{API}/admin/create-admin", json={
            "email": f"iter10_admin_weak_{TS}@example.com",
            "password": "short",
            "name": "Weak",
        }, headers=H(admin_tok))
        assert r.status_code in (400, 422), r.text

    def test_non_admin_forbidden(self, user_ctx):
        r = requests.post(f"{API}/admin/create-admin", json={
            "email": f"iter10_admin_forbid_{TS}@example.com",
            "password": "strong1234",
            "name": "Forbid",
        }, headers=H(user_ctx["token"]))
        assert r.status_code == 403

    def test_creates_admin(self, admin_tok):
        email = f"iter10_admin_{TS}@example.com"
        r = requests.post(f"{API}/admin/create-admin", json={
            "email": email, "password": "strong1234", "name": "Iter10 Admin",
        }, headers=H(admin_tok))
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["role"] == "admin"
        assert u["email"] == email
        # Duplicate
        r2 = requests.post(f"{API}/admin/create-admin", json={
            "email": email, "password": "strong1234", "name": "dup",
        }, headers=H(admin_tok))
        assert r2.status_code == 400


# ---------------- Payment creation + Choose method ---------------- #
class TestChooseMethod:
    def test_admin_create_payment_no_snap(self, admin_tok, service_and_sub):
        sub = service_and_sub["sub"]
        r = requests.post(f"{API}/admin/payments", json={
            "subscription_id": sub["id"], "amount": 45000, "period_label": "Jan 2026",
        }, headers=H(admin_tok))
        assert r.status_code == 200, r.text
        p = r.json()
        assert p.get("payment_method") in (None, "")
        assert not p.get("midtrans_redirect_url")
        assert int(p.get("base_amount", 0)) == 45000
        pytest.pid = p["id"]

    def test_choose_qris(self, user_ctx):
        r = requests.post(f"{API}/me/payments/{pytest.pid}/choose-method",
                          json={"method": "qris"}, headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["payment_method"] == "qris"
        assert int(p["amount"]) == 45000
        assert int(p.get("midtrans_fee", 0)) == 0

    def test_switch_to_midtrans(self, user_ctx):
        r = requests.post(f"{API}/me/payments/{pytest.pid}/choose-method",
                          json={"method": "midtrans"}, headers=H(user_ctx["token"]))
        # Midtrans sandbox may 401 → endpoint 502 (per spec, don't fail on that)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            p = r.json()
            assert p["payment_method"] == "midtrans"
            assert int(p["amount"]) == 45000 + 2250
            assert int(p["midtrans_fee"]) == 2250

    def test_unknown_method(self, user_ctx):
        r = requests.post(f"{API}/me/payments/{pytest.pid}/choose-method",
                          json={"method": "paypal"}, headers=H(user_ctx["token"]))
        assert r.status_code == 400

    def test_other_users_payment_forbidden(self, admin_tok):
        # Create a second user, try to choose method on first user's payment
        email2 = f"iter10_other_{TS}@example.com"
        r = requests.post(f"{API}/auth/register", json={
            "email": email2, "password": "userpass1234", "name": "Other",
        })
        assert r.status_code == 200
        tok2 = r.json()["token"]
        r = requests.post(f"{API}/me/payments/{pytest.pid}/choose-method",
                          json={"method": "qris"}, headers=H(tok2))
        assert r.status_code == 403


# ---------------- Receipt auto-approve ---------------- #
class TestReceiptAutoApprove:
    def test_upload_receipt_auto_paid(self, admin_tok, user_ctx, service_and_sub):
        # Create fresh payment
        r = requests.post(f"{API}/admin/payments", json={
            "subscription_id": service_and_sub["sub"]["id"], "amount": 45000, "period_label": "Feb 2026",
        }, headers=H(admin_tok))
        pid = r.json()["id"]
        # Ensure choose qris first (like frontend does)
        requests.post(f"{API}/me/payments/{pid}/choose-method",
                      json={"method": "qris"}, headers=H(user_ctx["token"]))
        # Upload receipt
        b64 = "data:image/png;base64," + base64.b64encode(b"receipt_bytes").decode()
        r = requests.post(f"{API}/me/payments/{pid}/receipt", json={
            "payment_id": pid, "file_base64": b64, "file_name": "receipt.png",
        }, headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "paid"
        # Verify via list
        r = requests.get(f"{API}/me/payments", headers=H(user_ctx["token"]))
        p = next((x for x in r.json() if x["id"] == pid), None)
        assert p and p["status"] == "paid"


# ---------------- (b) Partial subscription update ---------------- #
class TestPartialSubUpdate:
    def test_partial_status(self, admin_tok, service_and_sub):
        sid = service_and_sub["sub"]["id"]
        r = requests.patch(f"{API}/admin/subscriptions/{sid}",
                           json={"status": "paused"}, headers=H(admin_tok))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "paused"

    def test_partial_price_only(self, admin_tok, service_and_sub):
        sid = service_and_sub["sub"]["id"]
        r = requests.patch(f"{API}/admin/subscriptions/{sid}",
                           json={"price": 60000}, headers=H(admin_tok))
        assert r.status_code == 200, r.text
        assert int(r.json()["price"]) == 60000

    def test_partial_status_back_to_active(self, admin_tok, service_and_sub):
        sid = service_and_sub["sub"]["id"]
        r = requests.patch(f"{API}/admin/subscriptions/{sid}",
                           json={"status": "active"}, headers=H(admin_tok))
        assert r.status_code == 200


# ---------------- (d) Orphan cleanup ---------------- #
class TestOrphanCleanup:
    def test_no_orphan_user_id_zero(self, admin_tok):
        r = requests.get(f"{API}/admin/subscriptions", headers=H(admin_tok))
        assert r.status_code == 200, r.text
        subs = r.json()
        assert not any(s.get("user_id") == "0" for s in subs), "Orphan sub with user_id='0' still present"


# ---------------- Admin login persistence (no force-reset) ---------------- #
class TestAdminSeedNoForceReset:
    def test_admin_login_ok(self):
        r = requests.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
        })
        assert r.status_code == 200


# ---------------- Cleanup ---------------- #
def teardown_module(module):
    try:
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        tok = r.json()["token"]
        requests.post(f"{API}/admin/cleanup-test-users?prefix=Iter10", headers=H(tok))
        requests.post(f"{API}/admin/cleanup-test-users?prefix=iter10", headers=H(tok))
    except Exception:
        pass
