"""Iteration 18: idempotent verify-email, admin manual verify, join subscription, onboarding label, retry welcome."""
import os
import sys
import hashlib
import secrets
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import requests
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

sys.path.insert(0, "/app/backend")

_mongo = AsyncIOMotorClient(MONGO_URL)
_db = _mongo[DB_NAME]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register(email, name="Test User", password="TestPass123!"):
    r = requests.post(f"{API}/auth/register", json={"email": email, "name": name, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _get_user_id_by_email(email):
    async def _q():
        u = await _db.users.find_one({"email": email.lower()})
        return str(u["_id"]) if u else None
    return _run(_q())


def _insert_token(user_id, email, token_plain, expires_delta=timedelta(hours=1), used=False):
    th = hashlib.sha256(token_plain.encode()).hexdigest()
    async def _ins():
        await _db.email_verifications.insert_one({
            "user_id": user_id,
            "email": email.lower(),
            "token_hash": th,
            "expires_at": datetime.now(timezone.utc) + expires_delta,
            "used": used,
            "created_at": datetime.now(timezone.utc),
        })
    _run(_ins())
    return th


def _unique_email(prefix="iter18"):
    return f"TEST_{prefix}_{secrets.token_hex(4)}@example.com"


# ---------- P0: idempotent verify-email ----------
class TestVerifyEmailIdempotent:
    def test_idempotent_double_verify(self):
        email = _unique_email("idem")
        _register(email)
        user_id = _get_user_id_by_email(email)
        token = secrets.token_urlsafe(32)
        _insert_token(user_id, email, token)

        r1 = requests.post(f"{API}/auth/verify-email", json={"token": token})
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["ok"] is True
        assert d1["user"]["email_verified"] is True
        assert d1.get("token")

        # Second call SAME token — must still succeed (idempotent)
        r2 = requests.post(f"{API}/auth/verify-email", json={"token": token})
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["ok"] is True
        assert d2["user"]["email_verified"] is True

    def test_expired_token(self):
        email = _unique_email("exp")
        _register(email)
        user_id = _get_user_id_by_email(email)
        token = secrets.token_urlsafe(32)
        _insert_token(user_id, email, token, expires_delta=timedelta(hours=-1))
        r = requests.post(f"{API}/auth/verify-email", json={"token": token})
        assert r.status_code == 400
        assert "kadaluarsa" in r.text.lower()

    def test_invalid_token(self):
        r = requests.post(f"{API}/auth/verify-email", json={"token": "random_gibberish_" + secrets.token_hex(16)})
        assert r.status_code == 400
        assert "tidak valid" in r.text.lower()


# ---------- P6: admin manual verify ----------
class TestAdminManualVerify:
    def test_admin_verify_and_idempotent(self, admin_token):
        email = _unique_email("admv")
        _register(email)
        user_id = _get_user_id_by_email(email)

        # Insert a pending token to test invalidation
        token = secrets.token_urlsafe(32)
        _insert_token(user_id, email, token)

        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/admin/users/{user_id}/verify-email", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["user"]["email_verified"] is True

        # Pending token must now be used=True
        async def _q():
            return await _db.email_verifications.find_one({"user_id": user_id})
        rec = _run(_q())
        assert rec is not None and rec.get("used") is True

        # Second call: idempotent, already_verified True
        r2 = requests.post(f"{API}/admin/users/{user_id}/verify-email", headers=headers)
        assert r2.status_code == 200
        assert r2.json().get("already_verified") is True

    def test_non_admin_cannot_manual_verify(self):
        # Register + verify a user via admin, then use their token
        email = _unique_email("nonadm")
        _register(email)
        target_email = _unique_email("target")
        _register(target_email)
        target_id = _get_user_id_by_email(target_email)

        # Verify our attacker so they can login
        attacker_id = _get_user_id_by_email(email)
        async def _mark():
            await _db.users.update_one({"_id": ObjectId(attacker_id)}, {"$set": {"email_verified": True}})
        _run(_mark())

        lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass123!"})
        assert lr.status_code == 200, lr.text
        tok = lr.json()["token"]
        r = requests.post(f"{API}/admin/users/{target_id}/verify-email", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code in (401, 403), r.text


# ---------- P1: join subscription ----------
class TestJoinSubscription:
    def _get_service(self, min_dur=None):
        r = requests.get(f"{API}/services")
        assert r.status_code == 200
        svcs = [s for s in r.json() if s.get("active", True)]
        if min_dur is not None:
            svcs = [s for s in svcs if int(s.get("min_duration_months", 1) or 1) >= min_dur]
        assert svcs, "No services available"
        return svcs[0]

    def _fresh_verified_user(self, admin_token):
        email = _unique_email("join")
        _register(email)
        uid = _get_user_id_by_email(email)
        requests.post(f"{API}/admin/users/{uid}/verify-email", headers={"Authorization": f"Bearer {admin_token}"})
        lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass123!"})
        assert lr.status_code == 200
        return uid, lr.json()["token"], email

    def test_join_and_duplicate(self, admin_token):
        uid, utok, _ = self._fresh_verified_user(admin_token)
        svc = self._get_service()
        r = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": svc["id"], "duration_months": 3},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["subscription_id"]
        assert d["payment"]["id"]
        assert d["amount"] == int(svc["price_regular"]) * 3
        assert d["service_name"] == svc["name"]

        # DB checks
        async def _q():
            sub = await _db.subscriptions.find_one({"_id": ObjectId(d["subscription_id"])})
            pay = await _db.payments.find_one({"_id": ObjectId(d["payment"]["id"])})
            return sub, pay
        sub, pay = _run(_q())
        assert sub["status"] == "pending"
        assert sub["role"] == "regular"
        assert sub["duration_months"] == 3
        assert sub.get("group_id") in (None,)
        assert sub.get("self_join") is True
        assert pay["status"] == "pending"
        assert pay.get("payment_method") in (None,)

        # Duplicate
        r2 = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": svc["id"], "duration_months": 3},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert r2.status_code == 400
        assert "sudah punya" in r2.text.lower()

    def test_join_below_min_duration(self, admin_token):
        # Find or create a service with min_duration_months >=3
        async def _find_or_make():
            svc = await _db.services.find_one({"min_duration_months": {"$gte": 3}})
            if svc:
                return str(svc["_id"])
            # Create one via admin api
            return None
        svc_id = _run(_find_or_make())
        if not svc_id:
            headers = {"Authorization": f"Bearer {admin_token}"}
            payload = {
                "slug": f"test-min-{secrets.token_hex(3)}",
                "name": "TEST MinDur Svc",
                "description": "test",
                "price_regular": 50000,
                "price_group": 25000,
                "min_duration_months": 3,
                "active": True,
            }
            r = requests.post(f"{API}/admin/services", json=payload, headers=headers)
            assert r.status_code == 200, r.text
            svc_id = r.json()["id"]

        uid, utok, _ = self._fresh_verified_user(admin_token)
        r = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": svc_id, "duration_months": 1},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert r.status_code == 400
        assert "durasi minimum" in r.text.lower()

    def test_join_invalid_service(self, admin_token):
        _, utok, _ = self._fresh_verified_user(admin_token)
        fake_id = "0" * 24
        r = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": fake_id, "duration_months": 1},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert r.status_code == 404
        assert "tidak tersedia" in r.text.lower()


# ---------- P3: onboarding label ----------
class TestOnboardingLabel:
    def test_first_payment_label_and_done(self, admin_token):
        email = _unique_email("onb")
        _register(email)
        uid = _get_user_id_by_email(email)
        requests.post(f"{API}/admin/users/{uid}/verify-email", headers={"Authorization": f"Bearer {admin_token}"})
        lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass123!"})
        utok = lr.json()["token"]

        r = requests.get(f"{API}/me/onboarding", headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        steps = r.json().get("steps", [])
        fp = next((s for s in steps if s["key"] == "first_payment"), None)
        assert fp is not None
        assert fp["label"] == "Ikut patungan pertama (pilih layanan)"
        assert fp["done"] is False

        # Create a pending sub via join
        svcs = requests.get(f"{API}/services").json()
        svc = [s for s in svcs if s.get("active", True)][0]
        rj = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": svc["id"], "duration_months": svc.get("min_duration_months", 1)},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert rj.status_code == 200, rj.text

        r2 = requests.get(f"{API}/me/onboarding", headers={"Authorization": f"Bearer {utok}"})
        steps2 = r2.json().get("steps", [])
        fp2 = next((s for s in steps2 if s["key"] == "first_payment"), None)
        assert fp2["done"] is True, f"first_payment should be done after join, got {fp2}"


# ---------- P5: welcome retry ----------
class TestWelcomeRetry:
    def test_retry_function_callable(self):
        from server import _retry_pending_welcome_emails
        res = _run(_retry_pending_welcome_emails())
        assert isinstance(res, dict)

    def test_user_out_still_ok(self, admin_token):
        r = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        for u in r.json()[:5]:
            # welcome_email_retries / given_up should not break serialization
            assert "id" in u and "email" in u


# ---------- Regression ----------
class TestRegression:
    def test_login_admin(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200

    def test_register_flow(self):
        email = _unique_email("reg")
        r = requests.post(f"{API}/auth/register", json={"email": email, "name": "Reg", "password": "TestPass123!"})
        assert r.status_code == 200
        assert r.json().get("email_verification_sent") is True

    def test_services(self):
        r = requests.get(f"{API}/services")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_users_and_create(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/users", headers=h)
        assert r.status_code == 200
        email = _unique_email("admcreate")
        r = requests.post(f"{API}/admin/users", json={"email": email, "name": "AdmCreate", "password": "TestPass123!", "role": "user"}, headers=h)
        assert r.status_code == 200, r.text

    def test_renew(self, admin_token):
        # Create verified user, join, then renew
        email = _unique_email("renew")
        _register(email)
        uid = _get_user_id_by_email(email)
        requests.post(f"{API}/admin/users/{uid}/verify-email", headers={"Authorization": f"Bearer {admin_token}"})
        lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass123!"})
        utok = lr.json()["token"]
        svcs = requests.get(f"{API}/services").json()
        svc = [s for s in svcs if s.get("active", True)][0]
        rj = requests.post(f"{API}/me/subscriptions/join", json={"service_id": svc["id"], "duration_months": svc.get("min_duration_months", 1)}, headers={"Authorization": f"Bearer {utok}"})
        assert rj.status_code == 200
        sub_id = rj.json()["subscription_id"]
        rr = requests.post(f"{API}/me/subscriptions/{sub_id}/renew", json={"duration_months": 1}, headers={"Authorization": f"Bearer {utok}"})
        assert rr.status_code == 200, rr.text
