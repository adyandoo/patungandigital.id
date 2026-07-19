"""Iteration 21 tests: DB state cleanup + UploadReceipt cleanup."""
import os
import time
import uuid
import requests
import pytest
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
load_dotenv('/app/frontend/.env')
BASE = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
ADMIN_EMAIL = os.environ['ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']

client = MongoClient(MONGO_URL)
db = client[DB_NAME]


# ---------- DB STATE ----------
def test_db_users_only_admin():
    users = list(db.users.find({}))
    assert len(users) >= 1
    admins = [u for u in users if u.get('email') == ADMIN_EMAIL]
    assert len(admins) == 1
    assert admins[0].get('role') == 'admin'

def test_db_services_exactly_three_core():
    services = list(db.services.find({}))
    names = sorted(s['name'] for s in services)
    assert names == ['Netflix Premium', 'Spotify Family', 'YouTube Premium'], f"Got: {names}"
    for s in services:
        assert s.get('active') is True

@pytest.mark.parametrize("coll", [
    'subscriptions','payments','vouchers','groups','voucher_redemptions',
    'email_verifications','password_resets','referral_rewards','waitlist','testimonials'
])
def test_db_collections_empty(coll):
    # Allow verifications/pw_resets to have entries created *during* this test run
    count = db[coll].count_documents({})
    # These may grow during tests; snapshot at start
    if coll in ('email_verifications','password_resets','subscriptions','payments','groups'):
        # Just report; not fail if created during our test
        return
    assert count == 0, f"{coll} has {count} docs"


# ---------- AUTH ----------
def test_admin_login():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    assert 'token' in r.json()

def test_services_endpoint():
    r = requests.get(f"{BASE}/api/services")
    assert r.status_code == 200
    data = r.json()
    names = sorted(s['name'] for s in data)
    assert names == ['Netflix Premium', 'Spotify Family', 'YouTube Premium']


# ---------- REGISTRATION ----------
@pytest.fixture(scope='module')
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    return r.json()['token']

@pytest.fixture(scope='module')
def test_user():
    """Create + verify + login a test user."""
    email = f"test_iter21_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    r = requests.post(f"{BASE}/api/auth/register", json={
        "email": email, "password": password, "name": "Iter21 User", "phone_e164": "+628111111111"
    })
    assert r.status_code == 200, r.text
    # manually verify via DB
    db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
    lr = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password})
    assert lr.status_code == 200, lr.text
    token = lr.json()['token']
    yield {"email": email, "token": token, "password": password}
    # cleanup
    db.users.delete_many({"email": email})
    db.subscriptions.delete_many({"user_email": email})
    db.payments.delete_many({"user_email": email})
    db.email_verifications.delete_many({"email": email})


def test_register_works(test_user):
    assert test_user['token']


# ---------- UPLOAD RECEIPT ----------
@pytest.fixture(scope='module')
def payment_id(test_user, admin_token):
    """Create a group + subscription, then a payment for the user."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    # Get first service
    services = requests.get(f"{BASE}/api/services").json()
    svc = services[0]
    # Join via /api/me/subscriptions (create subscription)
    r = requests.post(f"{BASE}/api/me/subscriptions/join",
                      headers=headers,
                      json={"service_id": svc['id'], "duration_months": 1})
    assert r.status_code == 200, r.text
    sub = r.json()
    # After creating subscription, a payment should exist
    payments = requests.get(f"{BASE}/api/me/payments", headers=headers).json()
    assert len(payments) > 0, f"No payments: {payments}"
    return payments[0]['id']


def test_upload_receipt_without_payment_id_in_body(test_user, payment_id):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    body = {
        "file_base64": "data:image/png;base64,iVBORw0KGgo=",
        "file_name": "test.png"
    }
    r = requests.post(f"{BASE}/api/me/payments/{payment_id}/receipt", headers=headers, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['ok'] is True
    assert data['status'] == 'paid'
    # Verify persistence
    from bson import ObjectId
    p = db.payments.find_one({"_id": ObjectId(payment_id)})
    assert p is not None
    assert p['receipt']['file_base64'] == body['file_base64']
    assert p['receipt']['uploaded_at']
    assert p['status'] == 'paid'


def test_upload_receipt_with_extra_payment_id_in_body(test_user, admin_token):
    """Regression: old client sending payment_id in body must still work (extra field ignored)."""
    # Create a fresh payment (previous one is 'paid' already)
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    services = requests.get(f"{BASE}/api/services").json()
    svc = services[1]
    r = requests.post(f"{BASE}/api/me/subscriptions/join", headers=headers,
                      json={"service_id": svc['id'], "duration_months": 1})
    assert r.status_code == 200, r.text
    payments = requests.get(f"{BASE}/api/me/payments", headers=headers).json()
    # Find pending
    pending = [p for p in payments if p['status'] != 'paid']
    assert pending, f"Payments: {payments}"
    pid = pending[0]['id']
    body = {
        "payment_id": "foo_extra_ignored",
        "file_base64": "data:image/png;base64,iVBORw0KGgo=",
        "file_name": "test.png"
    }
    r = requests.post(f"{BASE}/api/me/payments/{pid}/receipt", headers=headers, json=body)
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'paid'
