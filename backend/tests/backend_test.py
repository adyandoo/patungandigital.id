"""Backend tests for patungandigital.id"""
import os
import time
import base64
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://group-stream-admin.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@patungandigital.id"
ADMIN_PASSWORD = "admin123"

TS = str(int(time.time()))
USER_EMAIL = f"test_user_{TS}@example.com"
USER_PASSWORD = "userpass123"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def user_ctx():
    """Register a fresh user and return (token, user_id)."""
    r = requests.post(f"{API}/auth/register", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD,
        "name": "Test User",
        "whatsapp": "+628123456789",
        "gender": "male",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], "user": data["user"]}


def auth_h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- Auth ---------------- #
class TestAuth:
    def test_register_returns_token_and_user(self, user_ctx):
        assert user_ctx["token"]
        assert user_ctx["user"]["email"] == USER_EMAIL
        assert user_ctx["user"]["role"] == "user"
        assert "password_hash" not in user_ctx["user"]

    def test_register_duplicate(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": USER_EMAIL, "password": USER_PASSWORD, "name": "dup"
        })
        assert r.status_code == 400

    def test_login_admin(self, admin_token):
        assert admin_token

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me(self, user_ctx):
        r = requests.get(f"{API}/auth/me", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == USER_EMAIL

    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_update_profile(self, user_ctx):
        r = requests.patch(f"{API}/auth/profile", headers=auth_h(user_ctx["token"]),
                           json={"name": "Updated Name", "whatsapp": "+628111", "gender": "female"})
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "Updated Name"
        assert d["whatsapp"] == "+628111"
        assert d["gender"] == "female"

    def test_change_password_wrong_current(self, user_ctx):
        r = requests.post(f"{API}/auth/change-password", headers=auth_h(user_ctx["token"]),
                          json={"current_password": "wrongpass", "new_password": "newpass123"})
        assert r.status_code == 400

    def test_change_password_success(self, user_ctx):
        new_pw = "newpass456"
        r = requests.post(f"{API}/auth/change-password", headers=auth_h(user_ctx["token"]),
                          json={"current_password": USER_PASSWORD, "new_password": new_pw})
        assert r.status_code == 200
        # login with new password
        r2 = requests.post(f"{API}/auth/login", json={"email": USER_EMAIL, "password": new_pw})
        assert r2.status_code == 200
        # restore for later tests
        requests.post(f"{API}/auth/change-password", headers=auth_h(r2.json()["token"]),
                      json={"current_password": new_pw, "new_password": USER_PASSWORD})


# ---------------- Services ---------------- #
class TestServicesPublic:
    def test_list_services(self):
        r = requests.get(f"{API}/services")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        slugs = {s["slug"] for s in data}
        assert {"netflix", "spotify", "youtube"}.issubset(slugs)
        # ensure _id not leaked
        for s in data:
            assert "_id" not in s
            assert "id" in s


# ---------------- Admin authorization ---------------- #
class TestAdminAuthorization:
    def test_non_admin_forbidden(self, user_ctx):
        r = requests.get(f"{API}/admin/users", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 403


# ---------------- Admin CRUD ---------------- #
class TestAdminUsers:
    def test_list(self, admin_token):
        r = requests.get(f"{API}/admin/users", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_create_update_delete(self, admin_token):
        email = f"TEST_admin_created_{TS}@example.com"
        r = requests.post(f"{API}/admin/users", headers=auth_h(admin_token), json={
            "email": email, "password": "pw123456", "name": "AdminCreated", "role": "user"
        })
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        # update
        r2 = requests.patch(f"{API}/admin/users/{uid}", headers=auth_h(admin_token),
                            json={"name": "Renamed"})
        assert r2.status_code == 200
        assert r2.json()["name"] == "Renamed"
        # delete
        r3 = requests.delete(f"{API}/admin/users/{uid}", headers=auth_h(admin_token))
        assert r3.status_code == 200


class TestAdminServices:
    def test_service_crud_and_plan(self, admin_token):
        slug = f"test-svc-{TS}"
        r = requests.post(f"{API}/admin/services", headers=auth_h(admin_token), json={
            "name": "TestSvc", "slug": slug, "price_regular": 10000, "price_host": 0
        })
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # update
        r2 = requests.patch(f"{API}/admin/services/{sid}", headers=auth_h(admin_token), json={
            "name": "TestSvcUpdated", "slug": slug, "price_regular": 15000, "price_host": 0
        })
        assert r2.status_code == 200
        assert r2.json()["name"] == "TestSvcUpdated"
        # plan
        rp = requests.post(f"{API}/admin/services/{sid}/plans", headers=auth_h(admin_token), json={
            "name": "TestPlan", "host_slots": 1, "regular_slots": 4
        })
        assert rp.status_code == 200
        plan_id = rp.json()["id"]
        rpl = requests.get(f"{API}/admin/services/{sid}/plans", headers=auth_h(admin_token))
        assert rpl.status_code == 200
        assert any(p["id"] == plan_id for p in rpl.json())
        rd = requests.delete(f"{API}/admin/plans/{plan_id}", headers=auth_h(admin_token))
        assert rd.status_code == 200
        # delete service
        rds = requests.delete(f"{API}/admin/services/{sid}", headers=auth_h(admin_token))
        assert rds.status_code == 200


# ---------------- Subscription + Payment ---------------- #
@pytest.fixture(scope="session")
def subscription(admin_token, user_ctx):
    # Get netflix service
    r = requests.get(f"{API}/services")
    svc = next(s for s in r.json() if s["slug"] == "netflix")
    body = {
        "user_id": user_ctx["user"]["id"],
        "service_id": svc["id"],
        "role": "regular",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "price": 45000,
        "status": "active",
    }
    r2 = requests.post(f"{API}/admin/subscriptions", headers=auth_h(admin_token), json=body)
    assert r2.status_code == 200, r2.text
    return r2.json()


class TestSubscriptions:
    def test_admin_list_has_join(self, admin_token, subscription):
        r = requests.get(f"{API}/admin/subscriptions", headers=auth_h(admin_token))
        assert r.status_code == 200
        items = r.json()
        found = next((s for s in items if s["id"] == subscription["id"]), None)
        assert found
        assert found.get("user")
        assert found.get("service")

    def test_user_sees_own_subs(self, user_ctx, subscription):
        r = requests.get(f"{API}/me/subscriptions", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert any(s["id"] == subscription["id"] for s in r.json())


@pytest.fixture(scope="session")
def payment(admin_token, subscription):
    r = requests.post(f"{API}/admin/payments", headers=auth_h(admin_token), json={
        "subscription_id": subscription["id"],
        "amount": 45000,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        "period_label": "Jan 2026",
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestPayments:
    def test_admin_list(self, admin_token, payment):
        r = requests.get(f"{API}/admin/payments", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert any(p["id"] == payment["id"] for p in r.json())

    def test_user_sees_own_payments(self, user_ctx, payment):
        r = requests.get(f"{API}/me/payments", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert any(p["id"] == payment["id"] for p in r.json())

    def test_update_status(self, admin_token, payment):
        r = requests.patch(f"{API}/admin/payments/{payment['id']}", headers=auth_h(admin_token),
                           json={"status": "paid"})
        assert r.status_code == 200
        assert r.json()["status"] == "paid"

    def test_upload_receipt_owner(self, user_ctx, payment):
        b64 = "data:image/png;base64," + base64.b64encode(b"fakeimg").decode()
        r = requests.post(f"{API}/me/payments/{payment['id']}/receipt",
                          headers=auth_h(user_ctx["token"]),
                          json={"payment_id": payment["id"], "file_base64": b64, "file_name": "receipt.png"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_upload_receipt_non_owner_forbidden(self, payment):
        # Register another user
        other_email = f"other_{TS}@example.com"
        rr = requests.post(f"{API}/auth/register", json={
            "email": other_email, "password": "pw123456", "name": "Other"
        })
        other_token = rr.json()["token"]
        b64 = "data:image/png;base64,AAAA"
        r = requests.post(f"{API}/me/payments/{payment['id']}/receipt",
                          headers=auth_h(other_token),
                          json={"payment_id": payment["id"], "file_base64": b64, "file_name": "x.png"})
        assert r.status_code == 403


class TestReminder:
    def test_get_config(self, admin_token):
        r = requests.get(f"{API}/admin/reminder-config", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert "days_before_due" in r.json()

    def test_put_config(self, admin_token):
        r = requests.put(f"{API}/admin/reminder-config", headers=auth_h(admin_token), json={
            "days_before_due": 5, "enable_email": True, "enable_whatsapp": True,
            "reminder_message": "Halo {name}, {service} {period} {due_date} Rp {amount}."
        })
        assert r.status_code == 200

    def test_send_reminder_mocked(self, admin_token, payment):
        r = requests.post(f"{API}/admin/send-reminder/{payment['id']}", headers=auth_h(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mocked") is True


class TestAdminStats:
    def test_stats(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers=auth_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        for k in ["users", "services", "active_subscriptions", "pending_payments"]:
            assert k in d
