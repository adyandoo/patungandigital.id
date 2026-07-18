"""Iteration 3 tests: Xendit webhook, Google exchange, Analytics, BSON dates."""
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
    email = f"iter3_{TS}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "pw123456", "name": "Iter3 User"
    })
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def netflix_svc():
    r = requests.get(f"{API}/services")
    return next(s for s in r.json() if s["slug"] == "netflix")


@pytest.fixture(scope="module")
def fresh_payment(admin_token, user_ctx, netflix_svc):
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
        "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "period_label": "Iter3 Test",
    })
    assert rp.status_code == 200, rp.text
    return rp.json()


class TestXenditWebhook:
    def test_ignored_when_not_pay_prefix(self):
        r = requests.post(f"{API}/webhooks/xendit", json={"external_id": "other-123", "status": "PAID"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "ignored" in (d.get("note") or "")

    def test_invalid_payment_id(self):
        r = requests.post(f"{API}/webhooks/xendit", json={"external_id": "pay-notanoid", "status": "PAID"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_paid_marks_payment(self, admin_token, fresh_payment):
        pid = fresh_payment["id"]
        r = requests.post(f"{API}/webhooks/xendit", json={"external_id": f"pay-{pid}", "status": "PAID"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["status"] == "paid"
        # Verify persisted
        rlist = requests.get(f"{API}/admin/payments", headers=auth_h(admin_token))
        p = next(p for p in rlist.json() if p["id"] == pid)
        assert p["status"] == "paid"
        assert p.get("xendit_paid_at")
        # log entry
        rl = requests.get(f"{API}/admin/logs?limit=100", headers=auth_h(admin_token))
        actions = [l["action"] for l in rl.json()["logs"]]
        assert "xendit_webhook" in actions

    def test_expired_marks_overdue(self, admin_token, user_ctx, netflix_svc):
        # create fresh payment for this
        body = {
            "user_id": user_ctx["user"]["id"],
            "service_id": netflix_svc["id"],
            "role": "regular",
            "start_date": datetime.now(timezone.utc).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "price": 45000, "status": "active",
        }
        rs = requests.post(f"{API}/admin/subscriptions", headers=auth_h(admin_token), json=body)
        sub_id = rs.json()["id"]
        rp = requests.post(f"{API}/admin/payments", headers=auth_h(admin_token), json={
            "subscription_id": sub_id, "amount": 10000,
            "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "period_label": "Iter3 Exp",
        })
        pid = rp.json()["id"]
        r = requests.post(f"{API}/webhooks/xendit", json={"external_id": f"pay-{pid}", "status": "EXPIRED"})
        assert r.status_code == 200
        assert r.json()["status"] == "overdue"


class TestGoogleExchange:
    def test_invalid_session_id_returns_401(self):
        r = requests.post(f"{API}/auth/google/exchange", json={"session_id": "fake-invalid-session"})
        assert r.status_code == 401, r.text


class TestAnalytics:
    def test_analytics_requires_admin(self, user_ctx):
        r = requests.get(f"{API}/admin/analytics", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 403

    def test_analytics_structure(self, admin_token):
        r = requests.get(f"{API}/admin/analytics", headers=auth_h(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "monthly" in d
        assert isinstance(d["monthly"], list)
        # 12 or 13 depending on cursor rollover; require between 12 and 14
        assert 12 <= len(d["monthly"]) <= 14
        for m in d["monthly"]:
            assert "label" in m and "revenue" in m and "count" in m
        assert "by_service" in d
        assert "status_distribution" in d
        totals = d["totals"]
        for k in ("total_revenue_paid", "paid_count", "avg_payment"):
            assert k in totals


class TestBsonDates:
    def test_due_date_returned_as_iso_string(self, admin_token, user_ctx, netflix_svc):
        body = {
            "user_id": user_ctx["user"]["id"],
            "service_id": netflix_svc["id"],
            "role": "regular",
            "start_date": datetime.now(timezone.utc).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "price": 45000, "status": "active",
        }
        rs = requests.post(f"{API}/admin/subscriptions", headers=auth_h(admin_token), json=body)
        sub_id = rs.json()["id"]
        due = (datetime.now(timezone.utc) + timedelta(days=2))
        rp = requests.post(f"{API}/admin/payments", headers=auth_h(admin_token), json={
            "subscription_id": sub_id, "amount": 45000,
            "due_date": due.isoformat(), "period_label": "BSON test",
        })
        assert rp.status_code == 200
        pid = rp.json()["id"]
        # via admin list, due_date should be serialized ISO
        rlist = requests.get(f"{API}/admin/payments", headers=auth_h(admin_token))
        p = next(p for p in rlist.json() if p["id"] == pid)
        assert p.get("due_date") is not None
        assert isinstance(p["due_date"], str)  # FastAPI serializes datetime to ISO string


class TestSchedulerDedupeBson:
    def test_scheduler_dedupe_with_bson_dates(self, admin_token, user_ctx, netflix_svc):
        # Ensure config window includes payment
        requests.put(f"{API}/admin/reminder-config", headers=auth_h(admin_token),
                     json={"days_before_due": 5, "enable_email": True, "enable_whatsapp": True,
                           "reminder_message": "Hi {name}"})
        body = {
            "user_id": user_ctx["user"]["id"],
            "service_id": netflix_svc["id"],
            "role": "regular",
            "start_date": datetime.now(timezone.utc).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "price": 45000, "status": "active",
        }
        rs = requests.post(f"{API}/admin/subscriptions", headers=auth_h(admin_token), json=body)
        sub_id = rs.json()["id"]
        rp = requests.post(f"{API}/admin/payments", headers=auth_h(admin_token), json={
            "subscription_id": sub_id, "amount": 45000,
            "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "period_label": "Sched BSON",
        })
        pid = rp.json()["id"]
        r1 = requests.post(f"{API}/admin/scheduler/run-now", headers=auth_h(admin_token))
        assert r1.status_code == 200
        sent1 = [s["payment_id"] for s in r1.json()["sent"]]
        assert pid in sent1
        r2 = requests.post(f"{API}/admin/scheduler/run-now", headers=auth_h(admin_token))
        sent2 = [s["payment_id"] for s in r2.json()["sent"]]
        assert pid not in sent2
