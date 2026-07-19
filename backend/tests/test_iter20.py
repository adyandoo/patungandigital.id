"""Iteration 20: Voucher CRUD/apply/remove, monthly leaderboard, admin sub PATCH, user self-renew always."""
import os
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


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _unique_email(prefix="iter20"):
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


def _fresh_verified_user(admin_token, prefix="v20"):
    email = _unique_email(prefix)
    _register(email)
    uid = _get_user_id_by_email(email)
    r = requests.post(f"{API}/admin/users/{uid}/verify-email", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass123!"})
    assert lr.status_code == 200
    return uid, lr.json()["token"], email


def _netflix_service():
    r = requests.get(f"{API}/services")
    assert r.status_code == 200
    svcs = [s for s in r.json() if s.get("active", True)]
    net = next((s for s in svcs if "netflix" in (s.get("name", "").lower())), None)
    return net or svcs[0]


def _join_sub(utok, service_id, months=3):
    r = requests.post(
        f"{API}/me/subscriptions/join",
        json={"service_id": service_id, "duration_months": months},
        headers={"Authorization": f"Bearer {utok}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_voucher(admin_headers, **kwargs):
    payload = {
        "description": kwargs.pop("description", "Test voucher"),
        "discount_amount": kwargs.pop("discount_amount", 10000),
        "max_uses": kwargs.pop("max_uses", 5),
        "valid_days": kwargs.pop("valid_days", 30),
    }
    payload.update(kwargs)
    r = requests.post(f"{API}/admin/vouchers", json=payload, headers=admin_headers)
    return r


# ---------------- Voucher CRUD ---------------- #
class TestVoucherCreate:
    def test_create_default(self, admin_headers):
        r = _create_voucher(admin_headers, discount_amount=10000, max_uses=5, valid_days=30, description="Global 10k")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "active"
        assert d["used_count"] == 0
        assert d["discount_amount"] == 10000
        assert d["max_uses"] == 5
        assert len(d["code"]) == 8
        # valid_until = now+30d (allow 2min drift)
        vu = datetime.fromisoformat(d["valid_until"].replace("Z", "+00:00"))
        if vu.tzinfo is None:
            vu = vu.replace(tzinfo=timezone.utc)
        expected = datetime.now(timezone.utc) + timedelta(days=30)
        assert abs((vu - expected).total_seconds()) < 300

    def test_create_zero_discount_400(self, admin_headers):
        r = _create_voucher(admin_headers, discount_amount=0, discount_percent=0)
        assert r.status_code == 400

    def test_create_duplicate_code_400(self, admin_headers):
        code = "TEST" + secrets.token_hex(3).upper()
        r1 = _create_voucher(admin_headers, code=code, discount_amount=1000)
        assert r1.status_code == 200
        r2 = _create_voucher(admin_headers, code=code, discount_amount=1000)
        assert r2.status_code == 400

    def test_create_targeted(self, admin_headers, admin_token):
        uid, _, _ = _fresh_verified_user(admin_token, "tvtgt")
        r = _create_voucher(admin_headers, applies_to_user_id=uid, discount_amount=5000)
        assert r.status_code == 200, r.text
        assert r.json()["applies_to_user_id"] == uid

    def test_create_targeted_invalid_user_404(self, admin_headers):
        fake = "0" * 24
        r = _create_voucher(admin_headers, applies_to_user_id=fake, discount_amount=5000)
        assert r.status_code == 404


class TestVoucherListPatchDelete:
    def test_list_includes_target_user_info(self, admin_headers, admin_token):
        uid, _, email = _fresh_verified_user(admin_token, "tvlist")
        v = _create_voucher(admin_headers, applies_to_user_id=uid, discount_amount=3000).json()
        r = requests.get(f"{API}/admin/vouchers", headers=admin_headers)
        assert r.status_code == 200
        rows = r.json()
        found = next((x for x in rows if x["id"] == v["id"]), None)
        assert found is not None
        assert found.get("target_user") is not None
        assert found["target_user"]["email"] == email.lower()

    def test_patch_disable_then_apply_blocked(self, admin_headers, admin_token):
        # Create voucher
        v = _create_voucher(admin_headers, discount_amount=5000).json()
        # Patch to disabled
        r = requests.patch(f"{API}/admin/vouchers/{v['id']}", json={"status": "disabled"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"
        # Verify via GET
        rows = requests.get(f"{API}/admin/vouchers", headers=admin_headers).json()
        got = next((x for x in rows if x["id"] == v["id"]), None)
        assert got and got["status"] == "disabled"
        # Try to apply - need user + sub + payment
        _, utok, _ = _fresh_verified_user(admin_token, "tvdis")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        pid = j["payment"]["id"]
        ar = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                           json={"code": v["code"]}, headers={"Authorization": f"Bearer {utok}"})
        assert ar.status_code == 400
        assert "tidak aktif" in ar.text.lower()

    def test_delete(self, admin_headers):
        v = _create_voucher(admin_headers, discount_amount=2000).json()
        r = requests.delete(f"{API}/admin/vouchers/{v['id']}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        rows = requests.get(f"{API}/admin/vouchers", headers=admin_headers).json()
        assert not any(x["id"] == v["id"] for x in rows)


class TestUserVouchers:
    def test_targeted_visible_to_owner_not_others(self, admin_headers, admin_token):
        uidA, utokA, _ = _fresh_verified_user(admin_token, "usrA")
        uidB, utokB, _ = _fresh_verified_user(admin_token, "usrB")
        v = _create_voucher(admin_headers, applies_to_user_id=uidA, discount_amount=7000).json()
        ra = requests.get(f"{API}/me/vouchers", headers={"Authorization": f"Bearer {utokA}"})
        assert ra.status_code == 200
        assert any(x["id"] == v["id"] for x in ra.json()), "Voucher not visible to owner"
        rowA = next(x for x in ra.json() if x["id"] == v["id"])
        assert rowA["is_redeemed"] is False
        assert rowA["is_expired"] is False
        rb = requests.get(f"{API}/me/vouchers", headers={"Authorization": f"Bearer {utokB}"})
        assert rb.status_code == 200
        assert not any(x["id"] == v["id"] for x in rb.json())


# ---------------- Voucher Apply/Remove ---------------- #
class TestVoucherApply:
    def test_apply_global_voucher_reduces_amount(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vapp")
        svc = _netflix_service()
        price = int(svc["price_regular"])
        assert price == 45000, f"expected Netflix price 45000, got {price}"
        j = _join_sub(utok, svc["id"], months=3)
        assert j["amount"] == 135000
        pid = j["payment"]["id"]
        v = _create_voucher(admin_headers, discount_amount=10000, max_uses=5).json()
        r = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                          json={"code": v["code"]},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["discount_applied"] == 10000
        assert d["new_amount"] == 125000
        assert d["original_amount"] == 135000

        # DB checks
        async def _q():
            pay = await _db.payments.find_one({"_id": ObjectId(pid)})
            vch = await _db.vouchers.find_one({"_id": ObjectId(v["id"])})
            return pay, vch
        pay, vch = _run(_q())
        assert pay["voucher_applied_id"] == v["id"]
        assert pay["voucher_code"] == v["code"]
        assert pay["voucher_discount_amount"] == 10000
        assert pay["amount"] == 125000
        assert vch["used_count"] == 1

    def test_apply_same_voucher_twice_same_user_blocked(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vdup")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        pid = j["payment"]["id"]
        v = _create_voucher(admin_headers, discount_amount=1000, max_uses=10).json()
        r1 = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                           json={"code": v["code"]},
                           headers={"Authorization": f"Bearer {utok}"})
        assert r1.status_code == 200, r1.text
        # Second payment for same user (via renew)
        subid = j["subscription_id"]
        r_renew = requests.post(f"{API}/me/subscriptions/{subid}/renew",
                                json={}, headers={"Authorization": f"Bearer {utok}"})
        assert r_renew.status_code == 200, r_renew.text
        pid2 = r_renew.json()["id"]
        r2 = requests.post(f"{API}/me/payments/{pid2}/apply-voucher",
                           json={"code": v["code"]},
                           headers={"Authorization": f"Bearer {utok}"})
        assert r2.status_code == 400
        assert "sudah pakai voucher ini" in r2.text.lower()

    def test_apply_to_other_users_payment_403(self, admin_headers, admin_token):
        _, utokA, _ = _fresh_verified_user(admin_token, "voA")
        _, utokB, _ = _fresh_verified_user(admin_token, "voB")
        svc = _netflix_service()
        j = _join_sub(utokA, svc["id"], months=1)
        pid_a = j["payment"]["id"]
        v = _create_voucher(admin_headers, discount_amount=1000).json()
        r = requests.post(f"{API}/me/payments/{pid_a}/apply-voucher",
                          json={"code": v["code"]},
                          headers={"Authorization": f"Bearer {utokB}"})
        assert r.status_code == 403

    def test_apply_to_paid_payment_400(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vpaid")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        pid = j["payment"]["id"]
        # Upload receipt to mark paid
        up = requests.post(f"{API}/me/payments/{pid}/receipt",
                           json={"payment_id": pid, "file_base64": "data:image/png;base64,iVBOR", "file_name": "r.png"},
                           headers={"Authorization": f"Bearer {utok}"})
        assert up.status_code == 200, up.text
        v = _create_voucher(admin_headers, discount_amount=1000).json()
        r = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                          json={"code": v["code"]},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 400
        assert "pending" in r.text.lower()

    def test_apply_when_already_has_voucher_400(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vexist")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        pid = j["payment"]["id"]
        v1 = _create_voucher(admin_headers, discount_amount=1000).json()
        v2 = _create_voucher(admin_headers, discount_amount=2000).json()
        r1 = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                           json={"code": v1["code"]},
                           headers={"Authorization": f"Bearer {utok}"})
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                           json={"code": v2["code"]},
                           headers={"Authorization": f"Bearer {utok}"})
        assert r2.status_code == 400
        assert "voucher lain" in r2.text.lower()

    def test_remove_voucher_restores_amount(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vrem")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=3)
        pid = j["payment"]["id"]
        base = j["amount"]
        v = _create_voucher(admin_headers, discount_amount=10000).json()
        ra = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                           json={"code": v["code"]},
                           headers={"Authorization": f"Bearer {utok}"})
        assert ra.status_code == 200
        rr = requests.post(f"{API}/me/payments/{pid}/remove-voucher",
                           headers={"Authorization": f"Bearer {utok}"})
        assert rr.status_code == 200, rr.text
        assert rr.json()["restored_amount"] == base

        async def _q():
            pay = await _db.payments.find_one({"_id": ObjectId(pid)})
            vch = await _db.vouchers.find_one({"_id": ObjectId(v["id"])})
            red = await _db.voucher_redemptions.find_one({"voucher_id": v["id"], "user_id": pay and pay.get("user_id"), "payment_id": pid})
            return pay, vch, red
        pay, vch, _red = _run(_q())
        assert pay["amount"] == base
        assert "voucher_applied_id" not in pay
        assert "voucher_code" not in pay
        assert "voucher_discount_amount" not in pay
        assert vch["used_count"] == 0
        # redemption entry deleted
        async def _q2():
            return await _db.voucher_redemptions.find_one({"voucher_id": v["id"], "payment_id": pid})
        assert _run(_q2()) is None

    def test_expired_voucher_blocked(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vexp")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        pid = j["payment"]["id"]
        v = _create_voucher(admin_headers, discount_amount=1000, valid_days=30).json()

        async def _expire():
            await _db.vouchers.update_one(
                {"_id": ObjectId(v["id"])},
                {"$set": {"valid_until": datetime.now(timezone.utc) - timedelta(days=1)}},
            )
        _run(_expire())
        r = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                          json={"code": v["code"]},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 400
        assert "expired" in r.text.lower()

    def test_max_uses_enforced(self, admin_headers, admin_token):
        _, utokA, _ = _fresh_verified_user(admin_token, "vmuA")
        _, utokB, _ = _fresh_verified_user(admin_token, "vmuB")
        svc = _netflix_service()
        jA = _join_sub(utokA, svc["id"], months=1)
        jB = _join_sub(utokB, svc["id"], months=1)
        v = _create_voucher(admin_headers, discount_amount=1000, max_uses=1).json()
        r1 = requests.post(f"{API}/me/payments/{jA['payment']['id']}/apply-voucher",
                           json={"code": v["code"]},
                           headers={"Authorization": f"Bearer {utokA}"})
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/me/payments/{jB['payment']['id']}/apply-voucher",
                           json={"code": v["code"]},
                           headers={"Authorization": f"Bearer {utokB}"})
        assert r2.status_code == 400
        assert "habis" in r2.text.lower()

    def test_percent_discount(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "vpct")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=3)
        assert j["amount"] == 135000
        pid = j["payment"]["id"]
        v = _create_voucher(admin_headers, discount_amount=0, discount_percent=10).json()
        r = requests.post(f"{API}/me/payments/{pid}/apply-voucher",
                          json={"code": v["code"]},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["discount_applied"] == 13500
        assert d["new_amount"] == 121500


# ---------------- Leaderboard ---------------- #
class TestLeaderboard:
    def test_run_now_and_idempotent(self, admin_headers):
        r1 = requests.post(f"{API}/admin/leaderboard/run-now", headers=admin_headers)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("ok") is True
        assert "period" in d1 or "last_period" in d1 or "period_label" in d1
        assert "awards" in d1
        assert isinstance(d1["awards"], list)

        r2 = requests.post(f"{API}/admin/leaderboard/run-now", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json().get("ok") is True

        # Verify state
        async def _q():
            return await _db.settings.find_one({"key": "leaderboard_state"})
        st = _run(_q())
        assert st is not None
        assert st.get("last_period") is not None

    def test_state_endpoint(self, admin_headers):
        # ensure at least one run has occurred
        requests.post(f"{API}/admin/leaderboard/run-now", headers=admin_headers)
        r = requests.get(f"{API}/admin/leaderboard/state", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "last_period" in d
        assert "last_run_at" in d
        assert "last_awards" in d
        assert isinstance(d["last_awards"], list)


# ---------------- Admin Sub PATCH edit ---------------- #
class TestAdminSubEdit:
    def test_patch_all_fields(self, admin_headers, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "seditt")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        sub_id = j["subscription_id"]
        new_start = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        new_end = datetime(2025, 7, 15, 0, 0, 0, tzinfo=timezone.utc)
        payload = {
            "start_date": new_start.isoformat(),
            "end_date": new_end.isoformat(),
            "duration_months": 6,
            "price": 50000,
            "status": "active",
        }
        r = requests.patch(f"{API}/admin/subscriptions/{sub_id}", json=payload, headers=admin_headers)
        assert r.status_code == 200, r.text

        # GET admin subs to verify
        rl = requests.get(f"{API}/admin/subscriptions", headers=admin_headers)
        assert rl.status_code == 200
        subs = rl.json()
        # id field may be 'id' or 'subscription_id'
        target = next((s for s in subs if s.get("id") == sub_id or s.get("_id") == sub_id), None)
        assert target is not None, f"sub {sub_id} not found in admin list"
        assert int(target.get("duration_months", 0)) == 6
        assert int(target.get("price", 0)) == 50000
        assert target.get("status") == "active"
        # Dates may be iso strings
        assert "2025-01-15" in str(target.get("start_date", ""))
        assert "2025-07-15" in str(target.get("end_date", ""))


# ---------------- User self-renew always ---------------- #
class TestUserSelfRenew:
    def test_renew_creates_payment(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "rnw")
        svc = _netflix_service()
        j = _join_sub(utok, svc["id"], months=1)
        sub_id = j["subscription_id"]
        pid1 = j["payment"]["id"]
        # Mark first payment paid so sub gets extended
        up = requests.post(f"{API}/me/payments/{pid1}/receipt",
                           json={"payment_id": pid1, "file_base64": "data:image/png;base64,iVBOR", "file_name": "r.png"},
                           headers={"Authorization": f"Bearer {utok}"})
        assert up.status_code == 200
        # Even for freshly-paid sub (nowhere near expiry), renew must succeed
        r = requests.post(f"{API}/me/subscriptions/{sub_id}/renew",
                          json={}, headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p.get("status") == "pending"
        assert p.get("id")
        assert p.get("amount", 0) > 0


# ---------------- Regression Iter19 ---------------- #
class TestRegressionIter19:
    def test_annual_bonus_12(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "reg12")
        svc = _netflix_service()
        price = int(svc["price_regular"])
        r = requests.post(f"{API}/me/subscriptions/join",
                          json={"service_id": svc["id"], "duration_months": 12},
                          headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == price * 11
        assert d["bonus_month_applied"] is True

    def test_referral_tiers(self, admin_token):
        _, utok, _ = _fresh_verified_user(admin_token, "regtr")
        r = requests.get(f"{API}/me/referral-stats", headers={"Authorization": f"Bearer {utok}"})
        assert r.status_code == 200
        d = r.json()
        tiers = d.get("tiers")
        assert isinstance(tiers, list) and len(tiers) == 3
        expected = [(1, 10, 1), (2, 15, 2), (3, 45, 5)]
        for t, (tier, refs, fm) in zip(tiers, expected):
            assert t["tier"] == tier
            assert t["referrals"] == refs
            assert t["free_months"] == fm

    def test_ttl_indexes(self):
        async def _q():
            return (await _db.email_verifications.index_information(),
                    await _db.password_resets.index_information())
        ev, pr = _run(_q())
        def has_ttl(info):
            for _, spec in info.items():
                key = dict(spec.get("key") or [])
                if "expires_at" in key and spec.get("expireAfterSeconds") == 86400:
                    return True
            return False
        assert has_ttl(ev)
        assert has_ttl(pr)
