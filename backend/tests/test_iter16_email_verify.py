"""Iter16 P0 email verification + P1 sitemap tests."""
import os, sys, hashlib, secrets, time, asyncio
import pytest, requests
from datetime import datetime, timezone, timedelta

BASE_URL = "http://localhost:8001"  # use local backend so DB queries hit same mongo

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
_sync_client = MongoClient(MONGO_URL)
_sync_db = _sync_client[DB_NAME]

class _DBWrap:
    def __getattr__(self, name):
        col = _sync_db[name]
        class _C:
            def find_one(_self, q): return col.find_one(q)
            def insert_one(_self, d): return col.insert_one(d)
            def delete_one(_self, q): return col.delete_one(q)
            def delete_many(_self, q): return col.delete_many(q)
            def count_documents(_self, q): return col.count_documents(q)
        return _C()

_DBW = _DBWrap()
def db(): return _DBW
def run(v): return v  # no-op: calls are now sync


def _unique_email():
    return f"test_iter16_{secrets.token_hex(4)}@example.com"


# --- P0: Register ---
def test_register_no_token_creates_verification():
    email = _unique_email()
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "testpass123", "name": "Iter16 Tester"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("email_verification_sent") is True
    assert "token" not in data  # NO auto-login
    # Verify user in db has email_verified=False, auth_provider='manual'
    user = run(db().users.find_one({"email": email}))
    assert user is not None
    assert user.get("email_verified") is False
    assert user.get("auth_provider") == "manual"
    # Verification record exists
    rec = run(db().email_verifications.find_one({"email": email}))
    assert rec is not None
    assert rec.get("used") is False


# --- P0: Login with unverified -> 403 ---
def test_login_unverified_blocked():
    email = _unique_email()
    requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123", "name": "T"})
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 403
    assert "verifikasi" in r.json().get("detail", "").lower()


# --- P0: Legacy user (no auth_provider) can still login ---
def test_legacy_user_without_auth_provider_can_login():
    import bcrypt as _b
    email = f"test_legacy_{secrets.token_hex(3)}@example.com"
    pw = "legacypass1"
    pwhash = _b.hashpw(pw.encode(), _b.gensalt()).decode()
    run(db().users.insert_one({
        "email": email, "password_hash": pwhash, "name": "Legacy", "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
        # NO email_verified, NO auth_provider
    }))
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    assert "token" in r.json()
    run(db().users.delete_one({"email": email}))


# --- P0: Admin login still works (legacy admin) ---
def test_admin_login_still_works():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@patungandigital.id",
        "password": "Adm!nPd-JavpOaidEa6wZgFnBS",
    })
    assert r.status_code == 200, r.text


# --- P0: verify-email happy path (via inserting known token) ---
def test_verify_email_success_then_reuse_fails():
    email = _unique_email()
    r = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123", "name": "V"})
    assert r.status_code == 200
    user = run(db().users.find_one({"email": email}))
    uid = str(user["_id"])
    # Insert known token directly so we can test verify
    raw_token = secrets.token_urlsafe(32)
    th = hashlib.sha256(raw_token.encode()).hexdigest()
    run(db().email_verifications.insert_one({
        "user_id": uid, "email": email, "token_hash": th,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "used": False, "created_at": datetime.now(timezone.utc),
    }))
    # Verify
    r = requests.post(f"{BASE_URL}/api/auth/verify-email", json={"token": raw_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("user") is not None
    assert body.get("token")
    # DB: user verified
    user2 = run(db().users.find_one({"email": email}))
    assert user2.get("email_verified") is True
    # Re-use same token -> 400
    r2 = requests.post(f"{BASE_URL}/api/auth/verify-email", json={"token": raw_token})
    assert r2.status_code == 400
    # Login after verify -> 200
    r3 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "testpass123"})
    assert r3.status_code == 200
    assert "token" in r3.json()


def test_verify_email_expired_token():
    email = _unique_email()
    requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123", "name": "E"})
    user = run(db().users.find_one({"email": email}))
    raw = secrets.token_urlsafe(32)
    th = hashlib.sha256(raw.encode()).hexdigest()
    run(db().email_verifications.insert_one({
        "user_id": str(user["_id"]), "email": email, "token_hash": th,
        "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "used": False, "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
    }))
    r = requests.post(f"{BASE_URL}/api/auth/verify-email", json={"token": raw})
    assert r.status_code == 400
    assert "kadaluarsa" in r.json().get("detail", "").lower()


def test_verify_email_invalid_token():
    r = requests.post(f"{BASE_URL}/api/auth/verify-email", json={"token": "not_a_real_token_xxx"})
    assert r.status_code == 400
    assert "tidak valid" in r.json().get("detail", "").lower()


# --- P0: Resend verification rate limiting ---
def test_resend_verification_rate_limited():
    email = _unique_email()
    requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123", "name": "R"})
    # Count current verification records
    before = run(db().email_verifications.count_documents({"email": email}))
    # Immediate resend within 3 min window -> rate_limited
    r = requests.post(f"{BASE_URL}/api/auth/resend-verification", json={"email": email})
    assert r.status_code == 200
    body = r.json()
    assert body.get("rate_limited") is True
    after = run(db().email_verifications.count_documents({"email": email}))
    assert after == before  # no new token inserted


def test_resend_verification_creates_new_when_no_recent():
    email = _unique_email()
    # Create user manually without triggering register (so no recent verification)
    import bcrypt as _b
    run(db().users.insert_one({
        "email": email, "password_hash": _b.hashpw(b"x", _b.gensalt()).decode(),
        "name": "R2", "role": "user", "email_verified": False, "auth_provider": "manual",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    r = requests.post(f"{BASE_URL}/api/auth/resend-verification", json={"email": email})
    assert r.status_code == 200
    assert not r.json().get("rate_limited")
    count = run(db().email_verifications.count_documents({"email": email}))
    assert count >= 1
    run(db().users.delete_one({"email": email}))


# --- P1: robots.txt and sitemap ---
def test_robots_txt_file_exists():
    p = "/app/frontend/public/robots.txt"
    assert os.path.exists(p)
    with open(p) as f: content = f.read()
    assert "Sitemap: https://patungandigital.id/api/sitemap.xml" in content
    assert "Disallow" in content


def test_sitemap_xml_valid():
    r = requests.get(f"{BASE_URL}/api/sitemap.xml")
    assert r.status_code == 200
    assert "<urlset" in r.text
    assert "<url>" in r.text


# --- Cleanup at end ---
def test_zzz_cleanup():
    run(db().users.delete_many({"email": {"$regex": "^test_iter16_"}}))
    run(db().users.delete_many({"email": {"$regex": "^test_legacy_"}}))
    run(db().email_verifications.delete_many({"email": {"$regex": "^test_"}}))
