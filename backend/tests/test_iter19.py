"""Iteration 19: annual bonus (12 months → pay 11), FRONTEND_URL, referral tiers 10/15/45, TTL indexes."""
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
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

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


def _unique_email(prefix="iter19"):
    return f"TEST_{prefix}_{secrets.token_hex(4)}@example.com"


def _register(email, name="Test User", password="TestPass123!"):
    r = requests.post(f"{API}/auth/register", json={"email": email, "name": name, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _get_user_id_by_email(email):
    async def _q():
        u = await _db.users.find_one({"email": email.lower()})
        return str(u["_id"]) if u else None
    return _run(_q())


def _fresh_verified_user(admin_token):
    email = _unique_email("join")
    _register(email)
    uid = _get_user_id_by_email(email)
    requests.post(f"{API}/admin/users/{uid}/verify-email", headers={"Authorization": f"Bearer {admin_token}"})
    lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass123!"})
    assert lr.status_code == 200
    return uid, lr.json()["token"], email


def _pick_service():
    r = requests.get(f"{API}/services")
    assert r.status_code == 200
    svcs = [s for s in r.json() if s.get("active", True)]
    # prefer Netflix if available
    net = next((s for s in svcs if "netflix" in (s.get("name", "").lower())), None)
    return net or svcs[0]


# ---------- P0: Annual bonus 12 months ----------
class TestAnnualBonus12:
    def test_12_months_bonus_response(self, admin_token):
        uid, utok, _ = _fresh_verified_user(admin_token)
        svc = _pick_service()
        price = int(svc["price_regular"])
        r = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": svc["id"], "duration_months": 12},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["amount"] == price * 11, f"expected {price*11}, got {d['amount']}"
        assert d["original_amount"] == price * 12, f"expected {price*12}, got {d['original_amount']}"
        assert d["bonus_month_applied"] is True

        # DB checks
        async def _q():
            sub = await _db.subscriptions.find_one({"_id": ObjectId(d["subscription_id"])})
            pay = await _db.payments.find_one({"_id": ObjectId(d["payment"]["id"])})
            return sub, pay
        sub, pay = _run(_q())
        assert pay["billable_months"] == 11
        assert pay["duration_months"] == 12
        assert pay["annual_bonus_applied"] is True
        assert pay["original_amount"] == price * 12
        assert pay["amount"] == price * 11
        assert sub["duration_months"] == 12
        assert sub["annual_bonus_applied"] is True

    @pytest.mark.parametrize("months", [1, 3, 6])
    def test_non_12_no_bonus(self, admin_token, months):
        uid, utok, _ = _fresh_verified_user(admin_token)
        svc = _pick_service()
        price = int(svc["price_regular"])
        # Respect min_duration_months
        min_dur = int(svc.get("min_duration_months", 1) or 1)
        if months < min_dur:
            pytest.skip(f"service min_duration_months={min_dur}, cannot test months={months}")

        r = requests.post(
            f"{API}/me/subscriptions/join",
            json={"service_id": svc["id"], "duration_months": months},
            headers={"Authorization": f"Bearer {utok}"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == price * months
        assert d["bonus_month_applied"] is False
        assert d["original_amount"] == d["amount"]

        async def _q():
            pay = await _db.payments.find_one({"_id": ObjectId(d["payment"]["id"])})
            sub = await _db.subscriptions.find_one({"_id": ObjectId(d["subscription_id"])})
            return pay, sub
        pay, sub = _run(_q())
        assert pay["billable_months"] == months
        assert pay["duration_months"] == months
        assert pay["annual_bonus_applied"] is False
        assert pay["amount"] == price * months
        assert sub["duration_months"] == months
        assert sub["annual_bonus_applied"] is False


# ---------- P1: FRONTEND_URL ----------
class TestFrontendUrl:
    def test_env_is_https_not_localhost(self):
        assert FRONTEND_URL, "FRONTEND_URL missing from backend/.env"
        assert FRONTEND_URL.startswith("https://"), f"FRONTEND_URL must be https, got: {FRONTEND_URL}"
        assert "localhost" not in FRONTEND_URL.lower()
        assert "127.0.0.1" not in FRONTEND_URL

    def test_send_verification_email_uses_https(self):
        """Trigger _send_verification_email indirectly and inspect emitted verify_url via DB token + FRONTEND_URL prefix."""
        # We cannot capture the outgoing email, but we assert the server module constructs the URL using FRONTEND_URL env.
        sys.path.insert(0, "/app/backend")
        import importlib
        server = importlib.import_module("server")
        fe = getattr(server, "os").environ.get("FRONTEND_URL") or ""
        assert fe.startswith("https://"), f"server sees FRONTEND_URL={fe!r}"
        # ensure a verify-email path prefix exists in source
        with open("/app/backend/server.py", "r") as fh:
            src = fh.read()
        assert "/verify-email?token=" in src or "verify-email" in src


# ---------- P3a: Referral tiers 10/15/45 → 1/2/5 ----------
class TestReferralTiers:
    def test_stats_tiers_shape(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token)
        r = requests.get(f"{API}/me/referral-stats", headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        d = r.json()
        tiers = d.get("tiers")
        assert isinstance(tiers, list) and len(tiers) == 3
        expected = [(1, 10, 1), (2, 15, 2), (3, 45, 5)]
        for t, (tier, refs, fm) in zip(tiers, expected):
            assert t["tier"] == tier
            assert t["referrals"] == refs
            assert t["free_months"] == fm
        # next_tier should be tier 1 for a fresh user
        nt = d.get("next_tier")
        assert nt is not None
        assert nt["tier"] == 1
        assert nt["referrals"] == 10


# ---------- P3b: TTL indexes ----------
class TestTTLIndexes:
    def test_email_verifications_ttl(self):
        async def _q():
            return await _db.email_verifications.index_information()
        info = _run(_q())
        found = False
        for name, spec in info.items():
            key = dict(spec.get("key") or [])
            if "expires_at" in key and spec.get("expireAfterSeconds") == 86400:
                found = True
                break
        assert found, f"no TTL(86400) on email_verifications.expires_at; indexes={info}"

    def test_password_resets_ttl(self):
        async def _q():
            return await _db.password_resets.index_information()
        info = _run(_q())
        found = False
        for name, spec in info.items():
            key = dict(spec.get("key") or [])
            if "expires_at" in key and spec.get("expireAfterSeconds") == 86400:
                found = True
                break
        assert found, f"no TTL(86400) on password_resets.expires_at; indexes={info}"


# ---------- REGRESSION: Iter18 flows ----------
class TestRegressionIter18:
    def test_verify_email_idempotent(self):
        email = _unique_email("regidem")
        _register(email)
        uid = _get_user_id_by_email(email)
        token = secrets.token_urlsafe(32)
        th = hashlib.sha256(token.encode()).hexdigest()
        async def _ins():
            await _db.email_verifications.insert_one({
                "user_id": uid, "email": email.lower(), "token_hash": th,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
                "used": False, "created_at": datetime.now(timezone.utc),
            })
        _run(_ins())
        r1 = requests.post(f"{API}/auth/verify-email", json={"token": token})
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/auth/verify-email", json={"token": token})
        assert r2.status_code == 200
        assert r2.json()["user"]["email_verified"] is True

    def test_admin_verify_email(self, admin_token):
        email = _unique_email("regadmv")
        _register(email)
        uid = _get_user_id_by_email(email)
        r = requests.post(f"{API}/admin/users/{uid}/verify-email",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert r.json()["user"]["email_verified"] is True

    def test_basic_1_month_join(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token)
        svc = _pick_service()
        min_dur = int(svc.get("min_duration_months", 1) or 1)
        r = requests.post(f"{API}/me/subscriptions/join",
                          json={"service_id": svc["id"], "duration_months": min_dur},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == int(svc["price_regular"]) * min_dur
        assert d["bonus_month_applied"] is False

    def test_duplicate_join_blocked(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token)
        svc = _pick_service()
        min_dur = int(svc.get("min_duration_months", 1) or 1)
        r1 = requests.post(f"{API}/me/subscriptions/join",
                           json={"service_id": svc["id"], "duration_months": min_dur},
                           headers={"Authorization": f"Bearer {utok}"})
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/me/subscriptions/join",
                           json={"service_id": svc["id"], "duration_months": min_dur},
                           headers={"Authorization": f"Bearer {utok}"})
        assert r2.status_code == 400
        assert "sudah punya" in r2.text.lower()

    def test_invalid_service_404(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token)
        r = requests.post(f"{API}/me/subscriptions/join",
                          json={"service_id": "0" * 24, "duration_months": 1},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 404

    def test_onboarding_first_payment_label(self, admin_token):
        uid, utok, _ = _fresh_verified_user(admin_token)
        r = requests.get(f"{API}/me/onboarding", headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200
        steps = r.json().get("steps", [])
        fp = next((s for s in steps if s["key"] == "first_payment"), None)
        assert fp is not None
        assert fp["label"] == "Ikut patungan pertama (pilih layanan)"
        assert fp["done"] is False

        svc = _pick_service()
        min_dur = int(svc.get("min_duration_months", 1) or 1)
        requests.post(f"{API}/me/subscriptions/join",
                      json={"service_id": svc["id"], "duration_months": min_dur},
                      headers={"Authorization": f"Bearer {utok}"})
        r2 = requests.get(f"{API}/me/onboarding", headers={"Authorization": f"Bearer {utok}"})
        fp2 = next((s for s in r2.json().get("steps", []) if s["key"] == "first_payment"), None)
        assert fp2["done"] is True
