"""Iter11 tests: bulk user CSV import + auto-invoice generator + config endpoints."""
import base64
import csv
import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@patungandigital.id"
ADMIN_PW = "Adm!nPd-JavpOaidEa6wZgFnBS"

RUN_ID = f"iter11{uuid.uuid4().hex[:6]}"


# ------------- Fixtures -------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def user_session(admin_session):
    """Create a plain user via admin, then log in as that user."""
    email = f"iter11user_{uuid.uuid4().hex[:6]}@example.com"
    r = admin_session.post(f"{BASE_URL}/api/admin/users", json={
        "email": email, "password": "userpass123", "name": f"Iter11 U {RUN_ID}", "role": "user",
    })
    assert r.status_code in (200, 201), r.text
    s = requests.Session()
    r2 = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "userpass123"})
    assert r2.status_code == 200
    return s


@pytest.fixture(scope="module")
def cleanup(admin_session):
    yield
    # Cleanup iter11 users + their subs + payments
    admin_session.post(f"{BASE_URL}/api/admin/cleanup-test-users", params={"prefix": "iter11"})
    admin_session.post(f"{BASE_URL}/api/admin/cleanup-test-users", params={"prefix": "Iter11"})


# ------------- Helpers -------------
def make_csv_b64(rows, header=None, as_data_url=False):
    header = header or ["name", "email", "username", "whatsapp", "gender", "password"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    raw = base64.b64encode(buf.getvalue().encode("utf-8")).decode()
    return f"data:text/csv;base64,{raw}" if as_data_url else raw


# ============== Template CSV ==============
class TestTemplate:
    def test_template_csv_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/users/template.csv")
        assert r.status_code == 200
        text = r.text
        # header + 2 sample rows
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        assert len(lines) >= 3
        header = lines[0].lower()
        for col in ["name", "email", "username", "whatsapp", "gender", "password"]:
            assert col in header, f"missing col {col} in header: {header}"

    def test_template_csv_non_admin(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/admin/users/template.csv")
        assert r.status_code == 403


# ============== General config ==============
class TestGeneralConfig:
    def test_get_default(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/general-config")
        assert r.status_code == 200
        data = r.json()
        assert "default_new_user_password" in data
        # length >=6 (default 'patungan123' is 11)
        assert len(data["default_new_user_password"]) >= 6

    def test_put_valid_persists(self, admin_session):
        new_pw = "patungan123"  # keep default so we don't disrupt anything
        r = admin_session.put(f"{BASE_URL}/api/admin/general-config",
                              json={"default_new_user_password": new_pw})
        assert r.status_code == 200
        r2 = admin_session.get(f"{BASE_URL}/api/admin/general-config")
        assert r2.json()["default_new_user_password"] == new_pw

    def test_put_short_password_rejected(self, admin_session):
        r = admin_session.put(f"{BASE_URL}/api/admin/general-config",
                              json={"default_new_user_password": "abc"})
        assert r.status_code == 422


# ============== Invoice config ==============
class TestInvoiceConfig:
    def test_get_default(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/invoice-config")
        assert r.status_code == 200
        data = r.json()
        assert "day_of_month" in data
        assert "due_days" in data
        assert "enabled" in data

    def test_put_valid(self, admin_session):
        r = admin_session.put(f"{BASE_URL}/api/admin/invoice-config",
                              json={"day_of_month": 1, "due_days": 7, "enabled": True})
        assert r.status_code == 200
        r2 = admin_session.get(f"{BASE_URL}/api/admin/invoice-config")
        assert r2.json() == {"day_of_month": 1, "due_days": 7, "enabled": True}

    @pytest.mark.parametrize("day", [0, 29])
    def test_put_day_out_of_range(self, admin_session, day):
        r = admin_session.put(f"{BASE_URL}/api/admin/invoice-config",
                              json={"day_of_month": day, "due_days": 7, "enabled": True})
        assert r.status_code == 422

    @pytest.mark.parametrize("due", [0, 61])
    def test_put_due_out_of_range(self, admin_session, due):
        r = admin_session.put(f"{BASE_URL}/api/admin/invoice-config",
                              json={"day_of_month": 1, "due_days": due, "enabled": True})
        assert r.status_code == 422


# ============== Payment config bounds ==============
class TestPaymentConfigBounds:
    @pytest.mark.parametrize("pct", [-1, 101, 200])
    def test_midtrans_fee_percent_bounds(self, admin_session, pct):
        r = admin_session.put(f"{BASE_URL}/api/admin/payment-config",
                              json={"midtrans_fee_percent": pct})
        assert r.status_code == 422, r.text

    def test_midtrans_fee_percent_valid(self, admin_session):
        r = admin_session.put(f"{BASE_URL}/api/admin/payment-config",
                              json={"midtrans_fee_percent": 5.0})
        assert r.status_code == 200


# ============== Bulk import ==============
class TestBulkImport:
    def test_import_missing_email_header(self, admin_session):
        # CSV with no email column
        payload = make_csv_b64([["Bob", "bob"]], header=["name", "username"])
        r = admin_session.post(f"{BASE_URL}/api/admin/users/import",
                               json={"file_base64": payload, "file_name": "bad.csv"})
        assert r.status_code == 400
        assert "email" in r.text.lower()

    def test_import_non_admin(self, user_session):
        payload = make_csv_b64([["Bob", "b@example.com", "", "", "", ""]])
        r = user_session.post(f"{BASE_URL}/api/admin/users/import",
                              json={"file_base64": payload})
        assert r.status_code == 403

    def test_import_data_url_and_default_password(self, admin_session):
        # Set known default password
        admin_session.put(f"{BASE_URL}/api/admin/general-config",
                          json={"default_new_user_password": "patungan123"})
        uniq = uuid.uuid4().hex[:6]
        rows = [
            [f"Iter11 A {uniq}", f"iter11_a_{uniq}@example.com", "", "", "", ""],  # empty pw
            [f"Iter11 B {uniq}", f"iter11_b_{uniq}@example.com", "", "", "", "customPW1"],
            ["Iter11 Bad", "not-an-email", "", "", "", ""],  # error
        ]
        payload = make_csv_b64(rows, as_data_url=True)
        r = admin_session.post(f"{BASE_URL}/api/admin/users/import",
                               json={"file_base64": payload, "file_name": "t.csv"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["summary"]["created"] == 2
        assert data["summary"]["errors"] >= 1
        # Verify user A can login with default password
        s = requests.Session()
        r2 = s.post(f"{BASE_URL}/api/auth/login",
                    json={"email": f"iter11_a_{uniq}@example.com", "password": "patungan123"})
        assert r2.status_code == 200, "default password should work for empty-pw import"

    def test_import_duplicate_email_skipped(self, admin_session):
        uniq = uuid.uuid4().hex[:6]
        email = f"iter11_dup_{uniq}@example.com"
        rows = [[f"Iter11 D1 {uniq}", email, "", "", "", ""]]
        # First import: creates
        r1 = admin_session.post(f"{BASE_URL}/api/admin/users/import",
                                json={"file_base64": make_csv_b64(rows)})
        assert r1.status_code == 200
        assert r1.json()["summary"]["created"] == 1
        # Second import same email: skipped
        r2 = admin_session.post(f"{BASE_URL}/api/admin/users/import",
                                json={"file_base64": make_csv_b64(rows)})
        assert r2.status_code == 200
        d = r2.json()
        assert d["summary"]["created"] == 0
        assert d["summary"]["skipped"] == 1

    def test_import_3_valid_plus_1_duplicate(self, admin_session):
        uniq = uuid.uuid4().hex[:6]
        # Pre-create one to be duplicate
        dup_email = f"iter11_pre_{uniq}@example.com"
        admin_session.post(f"{BASE_URL}/api/admin/users", json={
            "email": dup_email, "password": "userpass123", "name": f"Iter11 pre {uniq}", "role": "user"
        })
        rows = [
            [f"Iter11 N1 {uniq}", f"iter11_n1_{uniq}@example.com", "", "", "", ""],
            [f"Iter11 N2 {uniq}", f"iter11_n2_{uniq}@example.com", "", "", "", ""],
            [f"Iter11 N3 {uniq}", f"iter11_n3_{uniq}@example.com", "", "", "", ""],
            [f"Iter11 Dup {uniq}", dup_email, "", "", "", ""],
        ]
        r = admin_session.post(f"{BASE_URL}/api/admin/users/import",
                               json={"file_base64": make_csv_b64(rows)})
        assert r.status_code == 200
        d = r.json()
        assert d["summary"]["created"] == 3
        assert d["summary"]["skipped"] == 1


# ============== Invoice generator E2E ==============
class TestInvoiceGenerator:
    def test_non_admin_forbidden(self, user_session):
        r = user_session.post(f"{BASE_URL}/api/admin/invoices/generate-now")
        assert r.status_code == 403

    def test_generate_now_e2e_and_idempotent(self, admin_session, cleanup):
        # Ensure invoice-config enabled with due_days=7
        admin_session.put(f"{BASE_URL}/api/admin/invoice-config",
                          json={"day_of_month": 1, "due_days": 7, "enabled": True})

        # 1) Import 3 users
        uniq = uuid.uuid4().hex[:6]
        emails = [f"iter11_sub_{uniq}_{i}@example.com" for i in range(3)]
        rows = [[f"Iter11 Sub {uniq} {i}", emails[i], "", "", "", ""] for i in range(3)]
        r = admin_session.post(f"{BASE_URL}/api/admin/users/import",
                               json={"file_base64": make_csv_b64(rows)})
        assert r.status_code == 200
        assert r.json()["summary"]["created"] == 3

        # Get user ids
        users_list = admin_session.get(f"{BASE_URL}/api/admin/users").json()
        by_email = {u["email"]: u["id"] for u in users_list}
        user_ids = [by_email[e] for e in emails]

        # 2) Ensure a service exists (create one if needed)
        svcs = admin_session.get(f"{BASE_URL}/api/admin/services").json()
        if not svcs:
            r = admin_session.post(f"{BASE_URL}/api/admin/services", json={
                "name": "Iter11 Svc", "slug": f"iter11-svc-{uniq}",
                "description": "", "price_regular": 50000, "price_host": 100000,
                "min_duration_months": 1, "active": True,
            })
            assert r.status_code == 200
            svc_id = r.json()["id"]
        else:
            svc_id = svcs[0]["id"]

        from datetime import datetime, timezone, timedelta
        start = datetime.now(timezone.utc).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

        sub_ids = []
        prices = [45000, 55000, 65000]
        for uid, price in zip(user_ids, prices):
            r = admin_session.post(f"{BASE_URL}/api/admin/subscriptions", json={
                "user_id": uid, "service_id": svc_id, "role": "regular",
                "start_date": start, "end_date": end, "price": price, "status": "active",
            })
            assert r.status_code == 200, r.text
            sub_ids.append(r.json()["id"])

        # 3) First run — expect >=3 invoices created for our new subs (may include other subs too)
        r = admin_session.post(f"{BASE_URL}/api/admin/invoices/generate-now")
        assert r.status_code == 200
        d1 = r.json()
        assert d1.get("ok") is True
        assert "period" in d1
        assert isinstance(d1.get("created"), list)
        # All three of our sub_ids must have a corresponding pending, auto_generated payment
        payments = admin_session.get(f"{BASE_URL}/api/admin/payments").json()
        for sid, price in zip(sub_ids, prices):
            matches = [p for p in payments if p.get("subscription_id") == sid and p.get("period_label") == d1["period"]]
            assert len(matches) == 1, f"sub {sid}: expected 1 auto invoice, got {len(matches)}"
            m = matches[0]
            assert m["status"] == "pending"
            assert m["amount"] == price
            assert m["base_amount"] == price
            assert m.get("payment_method") in (None, "")
            assert m.get("auto_generated") is True
            assert m.get("period_label") == d1["period"]
            assert m.get("due_date")

        # 4) Second run — idempotent: none of our subs should get another invoice
        r = admin_session.post(f"{BASE_URL}/api/admin/invoices/generate-now")
        assert r.status_code == 200
        d2 = r.json()
        payments2 = admin_session.get(f"{BASE_URL}/api/admin/payments").json()
        for sid in sub_ids:
            matches = [p for p in payments2 if p.get("subscription_id") == sid and p.get("period_label") == d1["period"]]
            assert len(matches) == 1, f"sub {sid}: duplicated invoice after re-run (got {len(matches)})"

        # 5) Add a NEW active sub and re-run — only the new one gets created
        new_email = f"iter11_late_{uniq}@example.com"
        admin_session.post(f"{BASE_URL}/api/admin/users", json={
            "email": new_email, "password": "userpass123", "name": f"Iter11 Late {uniq}", "role": "user"
        })
        new_uid = [u["id"] for u in admin_session.get(f"{BASE_URL}/api/admin/users").json() if u["email"] == new_email][0]
        r = admin_session.post(f"{BASE_URL}/api/admin/subscriptions", json={
            "user_id": new_uid, "service_id": svc_id, "role": "regular",
            "start_date": start, "end_date": end, "price": 77000, "status": "active",
        })
        assert r.status_code == 200
        new_sub_id = r.json()["id"]

        r = admin_session.post(f"{BASE_URL}/api/admin/invoices/generate-now")
        assert r.status_code == 200
        d3 = r.json()
        # New sub should be in created; existing 3 should NOT (they'd be in skipped count)
        payments3 = admin_session.get(f"{BASE_URL}/api/admin/payments").json()
        new_matches = [p for p in payments3 if p.get("subscription_id") == new_sub_id and p.get("period_label") == d1["period"]]
        assert len(new_matches) == 1
        for sid in sub_ids:
            matches = [p for p in payments3 if p.get("subscription_id") == sid and p.get("period_label") == d1["period"]]
            assert len(matches) == 1
