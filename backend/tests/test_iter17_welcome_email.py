"""Iter17: Welcome email on verify-email endpoint tests.

Tests:
- verify-email marks welcome_email_sent=True + welcome_email_sent_at, generates referral_code
- Idempotent: reusing token returns 400
- Empty name fallback: does not crash
- No regression on register/login/resend-verification/forgot-password
"""
import os, sys, hashlib, secrets, re
from datetime import datetime, timezone, timedelta

import pytest, requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

# Use local backend for testing (same as iter16) since we need DB access
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
# But also fall back to local if the public URL differs — for consistency use local since
# DB operations must match backend's DB.
LOCAL_URL = "http://localhost:8001"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
_client = MongoClient(MONGO_URL)
_db = _client[DB_NAME]

TEST_EMAIL_PREFIX = "test_iter17_"


def _unique_email(tag: str = "") -> str:
    return f"{TEST_EMAIL_PREFIX}{tag}{secrets.token_hex(4)}@example.com"


def _register(email: str, name: str = "Iter17 Tester", pw: str = "testpass123") -> requests.Response:
    return requests.post(f"{LOCAL_URL}/api/auth/register", json={
        "email": email, "password": pw, "name": name
    })


def _insert_verify_token(user_id: str, email: str, hours_valid: int = 1) -> str:
    raw = secrets.token_urlsafe(32)
    th = hashlib.sha256(raw.encode()).hexdigest()
    _db.email_verifications.insert_one({
        "user_id": user_id,
        "email": email,
        "token_hash": th,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=hours_valid),
        "used": False,
        "created_at": datetime.now(timezone.utc),
    })
    return raw


# ---------------- Public URL smoke ----------------
def test_public_backend_reachable():
    r = requests.get(f"{BASE_URL}/api/services", timeout=15)
    assert r.status_code in (200, 401, 403), f"Public backend not reachable: {r.status_code}"


# ---------------- Core: verify-email sends welcome + marks flags ----------------
def test_verify_email_success_marks_welcome_and_referral():
    email = _unique_email("ok_")
    r = _register(email)
    assert r.status_code == 200, r.text
    user_before = _db.users.find_one({"email": email})
    assert user_before is not None
    uid = str(user_before["_id"])

    raw = _insert_verify_token(uid, email)
    r2 = requests.post(f"{LOCAL_URL}/api/auth/verify-email", json={"token": raw})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body.get("ok") is True
    assert body.get("user") is not None
    assert body.get("token")

    user_after = _db.users.find_one({"email": email})
    assert user_after.get("email_verified") is True
    assert user_after.get("welcome_email_sent") is True, "welcome_email_sent flag not set"
    sent_at = user_after.get("welcome_email_sent_at")
    assert sent_at, "welcome_email_sent_at missing"
    # Validate ISO timestamp
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", str(sent_at)), f"bad ISO ts: {sent_at}"

    # Referral code auto-generated (8 chars typical)
    rc = user_after.get("referral_code")
    assert rc, "referral_code missing"
    assert isinstance(rc, str) and 4 <= len(rc) <= 16, f"unexpected referral_code length: {rc}"


# ---------------- Idempotency: reuse token -> 400 ----------------
def test_verify_email_token_reuse_fails():
    email = _unique_email("reuse_")
    r = _register(email)
    assert r.status_code == 200
    uid = str(_db.users.find_one({"email": email})["_id"])
    raw = _insert_verify_token(uid, email)

    r1 = requests.post(f"{LOCAL_URL}/api/auth/verify-email", json={"token": raw})
    assert r1.status_code == 200, r1.text
    # Second call should fail
    r2 = requests.post(f"{LOCAL_URL}/api/auth/verify-email", json={"token": raw})
    assert r2.status_code == 400, r2.text
    assert "tidak valid" in r2.json().get("detail", "").lower() or "dipakai" in r2.json().get("detail", "").lower()


# ---------------- Empty/None name fallback ----------------
def test_verify_email_empty_name_does_not_crash():
    email = _unique_email("noname_")
    # Insert user directly with empty name
    import bcrypt as _b
    ins = _db.users.insert_one({
        "email": email,
        "password_hash": _b.hashpw(b"testpass123", _b.gensalt()).decode(),
        "name": "",
        "role": "user",
        "email_verified": False,
        "auth_provider": "manual",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    uid = str(ins.inserted_id)
    raw = _insert_verify_token(uid, email)
    r = requests.post(f"{LOCAL_URL}/api/auth/verify-email", json={"token": raw})
    assert r.status_code == 200, r.text
    user_after = _db.users.find_one({"email": email})
    assert user_after.get("email_verified") is True
    assert user_after.get("welcome_email_sent") is True


# ---------------- No regression: register ----------------
def test_register_still_works():
    email = _unique_email("reg_")
    r = _register(email)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("email_verification_sent") is True
    # No auto-login on register
    assert "token" not in body
    user = _db.users.find_one({"email": email})
    assert user and user.get("email_verified") is False


# ---------------- No regression: login (after verify) ----------------
def test_login_works_after_verify():
    email = _unique_email("login_")
    _register(email)
    uid = str(_db.users.find_one({"email": email})["_id"])
    raw = _insert_verify_token(uid, email)
    requests.post(f"{LOCAL_URL}/api/auth/verify-email", json={"token": raw})
    r = requests.post(f"{LOCAL_URL}/api/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    assert "token" in r.json()


def test_login_admin_still_works():
    r = requests.post(f"{LOCAL_URL}/api/auth/login", json={
        "email": "admin@patungandigital.id",
        "password": "Adm!nPd-JavpOaidEa6wZgFnBS",
    })
    assert r.status_code == 200, r.text
    assert "token" in r.json()


# ---------------- No regression: resend-verification ----------------
def test_resend_verification_returns_ok_uniform():
    email = _unique_email("resend_")
    _register(email)
    # Immediate resend — endpoint now returns uniform message (no rate_limited leak)
    r = requests.post(f"{LOCAL_URL}/api/auth/resend-verification", json={"email": email})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert "message" in body


def test_resend_verification_for_unknown_email_uniform():
    # Non-existent email should also return uniform ok
    r = requests.post(f"{LOCAL_URL}/api/auth/resend-verification", json={
        "email": f"nonexistent_{secrets.token_hex(4)}@example.com"
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ---------------- No regression: forgot-password ----------------
def test_forgot_password_endpoint_exists():
    email = _unique_email("forgot_")
    _register(email)
    r = requests.post(f"{LOCAL_URL}/api/auth/forgot-password", json={"email": email})
    # Endpoint should exist and return 200 (uniform response) or 202
    assert r.status_code in (200, 202), f"forgot-password broken: {r.status_code} {r.text}"


# ---------------- Invalid token still 400 ----------------
def test_verify_email_invalid_token():
    r = requests.post(f"{LOCAL_URL}/api/auth/verify-email", json={"token": "definitely_not_valid_zzz"})
    assert r.status_code == 400


# ---------------- Cleanup ----------------
def test_zzz_cleanup():
    _db.users.delete_many({"email": {"$regex": f"^{TEST_EMAIL_PREFIX}"}})
    _db.email_verifications.delete_many({"email": {"$regex": f"^{TEST_EMAIL_PREFIX}"}})
    _db.password_resets.delete_many({"email": {"$regex": f"^{TEST_EMAIL_PREFIX}"}}) if "password_resets" in _db.list_collection_names() else None
