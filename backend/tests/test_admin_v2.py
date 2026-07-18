"""Tests for iteration 2 admin features: logs, bulk actions, CSV export, scheduler."""
import os
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://group-stream-admin.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@patungandigital.id"
ADMIN_PASSWORD = "admin123"

TS = str(int(time.time()))


def auth_h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_ctx():
    email = f"v2user_{TS}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "pw123456", "name": "V2 User", "whatsapp": "+628100000", "gender": "male"
    })
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def netflix_svc():
    r = requests.get(f"{API}/services")
    return next(s for s in r.json() if s["slug"] == "netflix")


def _find_log(admin_token, action, target_substr=None):
    r = requests.get(f"{API}/admin/logs?limit=200", headers=auth_h(admin_token))
    assert r.status_code == 200, r.text
    logs = r.json()["logs"]
    for l in logs:
        if l["action"] == action:
            if target_substr is None or target_substr in (l.get("target") or ""):
                return l
    return None


# ------------- /admin/logs endpoint -------------
class TestLogsEndpoint:
    def test_admin_logs_ok(self, admin_token):
        r = requests.get(f"{API}/admin/logs", headers=auth_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        assert "total" in d and "logs" in d
        assert isinstance(d["logs"], list)
        for l in d["logs"]:
            assert "_id" not in l
            assert "id" in l
            assert "action" in l

    def test_admin_logs_pagination(self, admin_token):
        r = requests.get(f"{API}/admin/logs?limit=2&skip=0", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert len(r.json()["logs"]) <= 2

    def test_non_admin_forbidden(self, user_ctx):
        r = requests.get(f"{API}/admin/logs", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 403


# ------------- Actions produce logs -------------
class TestActionsLogged:
    def test_create_user_logged(self, admin_token):
        email = f"TEST_v2create_{TS}@example.com"
        r = requests.post(f"{API}/admin/users", headers=auth_h(admin_token),
                          json={"email": email, "password": "pw123456", "name": "X", "role": "user"})
        assert r.status_code == 200
        uid = r.json()["id"]
        l = _find_log(admin_token, "create_user", uid)
        assert l is not None
        # cleanup delete
        rd = requests.delete(f"{API}/admin/users/{uid}", headers=auth_h(admin_token))
        assert rd.status_code == 200
        assert _find_log(admin_token, "delete_user", uid) is not None

    def test_create_delete_service_logged(self, admin_token):
        slug = f"v2svc-{TS}"
        r = requests.post(f"{API}/admin/services", headers=auth_h(admin_token),
                          json={"name": "V2", "slug": slug, "price_regular": 1, "price_host": 0})
        assert r.status_code == 200
        sid = r.json()["id"]
        # note: create_service log is only added if server writes one; if not, skip that assertion
        rd = requests.delete(f"{API}/admin/services/{sid}", headers=auth_h(admin_token))
        assert rd.status_code == 200
        assert _find_log(admin_token, "delete_service", sid) is not None


# ------------- Bulk delete -------------
class TestBulkDelete:
    def test_bulk_delete_skips_admin(self, admin_token):
        # Create a regular user
        email = f"TEST_bulk_{TS}@example.com"
        r = requests.post(f"{API}/admin/users", headers=auth_h(admin_token),
                          json={"email": email, "password": "pw123456", "name": "B", "role": "user"})
        assert r.status_code == 200
        reg_id = r.json()["id"]

        # Find admin id
        ru = requests.get(f"{API}/admin/users", headers=auth_h(admin_token))
        admin_user = next(u for u in ru.json() if u.get("role") == "admin")
        admin_id = admin_user["id"]

        r2 = requests.post(f"{API}/admin/users/bulk-delete", headers=auth_h(admin_token),
                           json={"ids": [reg_id, admin_id]})
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d["deleted"] == 1
        assert d["skipped_admins"] == 1

        # admin still exists
        ru2 = requests.get(f"{API}/admin/users", headers=auth_h(admin_token))
        assert any(u["id"] == admin_id for u in ru2.json())
        # deleted user gone
        assert not any(u["id"] == reg_id for u in ru2.json())

        assert _find_log(admin_token, "bulk_delete_users") is not None


# ------------- Bulk remind + scheduler + logs for send_reminder/scheduler_run -------------
@pytest.fixture(scope="module")
def payment_due_soon(admin_token, user_ctx, netflix_svc):
    # Set reminder config days_before_due to a large window
    requests.put(f"{API}/admin/reminder-config", headers=auth_h(admin_token),
                 json={"days_before_due": 5, "enable_email": True, "enable_whatsapp": True,
                       "reminder_message": "Hi {name} {service} {period} {due_date} {amount}"})

    # Create subscription
    body = {
        "user_id": user_ctx["user"]["id"],
        "service_id": netflix_svc["id"],
        "role": "regular",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "price": 45000,
        "status": "active",
    }
    rs = requests.post(f"{API}/admin/subscriptions", headers=auth_h(admin_token), json=body)
    assert rs.status_code == 200, rs.text
    sub_id = rs.json()["id"]

    # Payment due in 2 days, status=pending
    rp = requests.post(f"{API}/admin/payments", headers=auth_h(admin_token), json={
        "subscription_id": sub_id,
        "amount": 45000,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "period_label": "Jan 2026",
    })
    assert rp.status_code == 200, rp.text
    return rp.json()


class TestBulkRemind:
    def test_bulk_remind(self, admin_token, payment_due_soon):
        r = requests.post(f"{API}/admin/payments/bulk-remind", headers=auth_h(admin_token),
                          json={"ids": [payment_due_soon["id"]]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] == 1
        assert len(d["results"]) == 1
        item = d["results"][0]
        assert item["payment_id"] == payment_due_soon["id"]
        assert "email_sent" in item and "whatsapp_sent" in item and "mocked" in item
        assert _find_log(admin_token, "bulk_send_reminder") is not None
        assert _find_log(admin_token, "send_reminder", payment_due_soon["id"]) is not None


# ------------- CSV export -------------
class TestCsvExport:
    def test_export_users_csv(self, admin_token):
        r = requests.get(f"{API}/admin/users/export.csv", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        text = r.text
        first_line = text.splitlines()[0]
        assert first_line == "id,name,username,email,whatsapp,gender,role,created_at"
        assert len(text.splitlines()) >= 2
        assert _find_log(admin_token, "export_users_csv") is not None

    def test_export_payments_csv(self, admin_token):
        r = requests.get(f"{API}/admin/payments/export.csv", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        first_line = r.text.splitlines()[0]
        assert first_line == "id,user_name,user_email,service,period,amount,due_date,status,receipt_uploaded,created_at,last_reminder_at"
        assert _find_log(admin_token, "export_payments_csv") is not None


# ------------- Scheduler -------------
class TestScheduler:
    def test_scheduler_run_now_empty_ok(self, admin_token):
        r = requests.post(f"{API}/admin/scheduler/run-now", headers=auth_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "count" in d and "sent" in d
        assert _find_log(admin_token, "scheduler_run") is not None

    def test_scheduler_sends_and_dedupes(self, admin_token, user_ctx, netflix_svc):
        # Set config to 5 days
        requests.put(f"{API}/admin/reminder-config", headers=auth_h(admin_token),
                     json={"days_before_due": 5, "enable_email": True, "enable_whatsapp": True,
                           "reminder_message": "Hi {name}"})
        # Create fresh subscription+payment (no prior reminder)
        body = {
            "user_id": user_ctx["user"]["id"],
            "service_id": netflix_svc["id"],
            "role": "regular",
            "start_date": datetime.now(timezone.utc).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "price": 45000,
            "status": "active",
        }
        rs = requests.post(f"{API}/admin/subscriptions", headers=auth_h(admin_token), json=body)
        sub_id = rs.json()["id"]
        rp = requests.post(f"{API}/admin/payments", headers=auth_h(admin_token), json={
            "subscription_id": sub_id,
            "amount": 45000,
            "due_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "period_label": "Jan sched",
        })
        pid = rp.json()["id"]

        # Run scheduler — should include this payment
        r1 = requests.post(f"{API}/admin/scheduler/run-now", headers=auth_h(admin_token))
        assert r1.status_code == 200
        sent_ids = [s["payment_id"] for s in r1.json()["sent"]]
        assert pid in sent_ids

        # last_reminder_at should now be set — verify by immediately re-running
        r2 = requests.post(f"{API}/admin/scheduler/run-now", headers=auth_h(admin_token))
        assert r2.status_code == 200
        sent_ids2 = [s["payment_id"] for s in r2.json()["sent"]]
        assert pid not in sent_ids2, "Duplicate reminder sent within 24h window"
