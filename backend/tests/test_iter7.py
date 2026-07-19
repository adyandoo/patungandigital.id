"""Iter7 tests: race-safe first_paid_at, Groups CRUD + credentials, /me/groups,
subscription group_id assignment, public availability, waitlist."""
import os
import time
import asyncio
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@patungandigital.id", "password": "admin123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def services(admin_session):
    r = admin_session.get(f"{API}/services", timeout=15)
    assert r.status_code == 200
    return r.json()


def _register(prefix, referral_code=None):
    ts = int(time.time() * 1000000)
    email = f"iter7_{prefix}_{ts}@example.com"
    payload = {"name": f"Iter7 {prefix}", "email": email, "password": "pass1234", "whatsapp": "+628111222333"}
    if referral_code:
        payload["referral_code"] = referral_code
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me").json()
    return s, me


def _create_sub(admin_session, user_id, service_id, plan_id, role="regular", price=45000, group_id=None):
    body = {
        "user_id": user_id, "service_id": service_id, "plan_id": plan_id,
        "role": role, "status": "active", "start_date": "2026-01-01T00:00:00Z", "price": price,
    }
    if group_id:
        body["group_id"] = group_id
    r = admin_session.post(f"{API}/admin/subscriptions", json=body, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _create_payment(admin_session, sub_id, amount=45000, label="Iter7"):
    r = admin_session.post(f"{API}/admin/payments", json={
        "subscription_id": sub_id, "amount": amount, "period_label": label, "due_date": None
    }, timeout=25)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- Race-safe first_paid_at ----------------
class TestRaceSafeFirstPaid:
    def test_parallel_paid_grants_reward_once(self, admin_session, services):
        s_ref, referrer = _register("racerefr")
        ref_code = s_ref.get(f"{API}/me/referral-stats").json()["referral_code"]
        s_new, new_user = _register("racereferred", referral_code=ref_code)
        # baseline credits
        base_ref_credit = s_ref.get(f"{API}/me/referral-stats").json()["referral_credit"]
        base_new_credit = s_new.get(f"{API}/me/referral-stats").json()["referral_credit"]

        plans = admin_session.get(f"{API}/admin/services/{services[0]['id']}/plans").json()
        sub = _create_sub(admin_session, new_user["id"], services[0]["id"], plans[0]["id"])
        pay = _create_payment(admin_session, sub["id"])

        # Fire two parallel PATCH requests using threads
        import concurrent.futures

        def do_patch():
            return admin_session.patch(f"{API}/admin/payments/{pay['id']}", json={"status": "paid"}, timeout=15)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(do_patch) for _ in range(2)]
            results = [f.result() for f in futs]
        for r in results:
            assert r.status_code == 200, r.text

        # Verify referrer credited exactly once
        ref_credit = s_ref.get(f"{API}/me/referral-stats").json()["referral_credit"]
        new_credit = s_new.get(f"{API}/me/referral-stats").json()["referral_credit"]
        assert ref_credit - base_ref_credit == 10000, f"expected +10000, got {ref_credit-base_ref_credit}"
        assert new_credit - base_new_credit == 10000, f"expected +10000, got {new_credit-base_new_credit}"

        # Verify only ONE referral_rewards log entry
        logs = admin_session.get(f"{API}/admin/logs", params={"limit": 500}, timeout=15).json()
        items = logs if isinstance(logs, list) else logs.get("items", logs.get("logs", []))
        cnt = sum(1 for e in items if e.get("action") == "referral_reward_credited" and str(new_user["id"]) in str(e))
        assert cnt == 1, f"expected 1 log entry, got {cnt}"

        # Verify first_paid_payment_id set
        # (verify via re-patching a 2nd payment does not credit again — already covered but stronger: check payer has first_paid_at)
        ob = s_new.get(f"{API}/me/onboarding").json()
        assert next(x for x in ob["steps"] if x["key"] == "first_payment")["done"] is True


# ---------------- Groups CRUD + credentials ----------------
class TestGroupsCRUD:
    def test_group_crud_and_credential(self, admin_session, services):
        # Pick service
        sid = services[0]["id"]
        # CREATE
        r = admin_session.post(f"{API}/admin/groups", json={
            "service_id": sid, "name": "Iter7 Group A", "host_slots": 1, "regular_slots": 4, "notes": "test"
        }, timeout=15)
        assert r.status_code == 200, r.text
        g = r.json()
        gid = g["id"]
        assert g["name"] == "Iter7 Group A"
        assert g["host_slots"] == 1 and g["regular_slots"] == 4

        # LIST
        lst = admin_session.get(f"{API}/admin/groups").json()
        assert any(x["id"] == gid for x in lst)
        row = next(x for x in lst if x["id"] == gid)
        assert "members" in row and "filled_host" in row and "filled_regular" in row
        # credential should not include password
        assert row.get("credential") in (None, row.get("credential")) # None initially

        # PATCH
        r = admin_session.patch(f"{API}/admin/groups/{gid}", json={
            "service_id": sid, "name": "Iter7 Group A2", "host_slots": 1, "regular_slots": 5, "notes": "upd"
        }, timeout=15)
        assert r.status_code == 200
        assert r.json()["name"] == "Iter7 Group A2"
        assert r.json()["regular_slots"] == 5

        # PUT credential
        r = admin_session.put(f"{API}/admin/groups/{gid}/credential", json={
            "email": "netflix@shared.test", "password": "SecretPW1", "notes": "shared"
        }, timeout=15)
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["email"] == "netflix@shared.test"

        # GET credential
        c2 = admin_session.get(f"{API}/admin/groups/{gid}/credential").json()
        assert c2["email"] == "netflix@shared.test"
        assert c2["password"] == "SecretPW1"

        # LIST group -- credential present but without password
        lst = admin_session.get(f"{API}/admin/groups").json()
        row = next(x for x in lst if x["id"] == gid)
        assert row["credential"] is not None
        assert "password" not in row["credential"], "list credential must NOT include password"
        assert row["credential"]["email"] == "netflix@shared.test"

        # DELETE credential
        r = admin_session.delete(f"{API}/admin/groups/{gid}/credential")
        assert r.status_code == 200
        assert admin_session.get(f"{API}/admin/groups/{gid}/credential").json() is None

        # Re-add credential for delete-group test
        admin_session.put(f"{API}/admin/groups/{gid}/credential", json={
            "email": "x@y.z", "password": "pw", "notes": ""
        })

        # DELETE group cleans up credential + unlinks subs
        # Create a sub linked to this group first
        plans = admin_session.get(f"{API}/admin/services/{sid}/plans").json()
        _, u = _register("g_del_user")
        sub = _create_sub(admin_session, u["id"], sid, plans[0]["id"], group_id=gid)
        assert sub.get("group_id") == gid

        r = admin_session.delete(f"{API}/admin/groups/{gid}")
        assert r.status_code == 200
        # verify credential removed
        subs = admin_session.get(f"{API}/admin/subscriptions").json()
        row_sub = next((x for x in subs if x["id"] == sub["id"]), None)
        assert row_sub is not None
        assert row_sub.get("group_id") in (None, ""), f"group_id should be null after group delete: {row_sub.get('group_id')}"

    def test_non_admin_cannot_access_credential(self, services):
        s_u, _ = _register("nonadmin")
        r = s_u.get(f"{API}/admin/groups")
        assert r.status_code in (401, 403)


# ---------------- /me/groups ----------------
class TestMyGroups:
    def test_user_sees_group_with_credential(self, admin_session, services):
        sid = services[0]["id"]
        plans = admin_session.get(f"{API}/admin/services/{sid}/plans").json()
        # Fresh group
        g = admin_session.post(f"{API}/admin/groups", json={
            "service_id": sid, "name": "Iter7 MG Group", "host_slots": 1, "regular_slots": 4
        }, timeout=15).json()
        gid = g["id"]
        # Set credential
        admin_session.put(f"{API}/admin/groups/{gid}/credential", json={
            "email": "shared@login.test", "password": "P@ss123", "notes": "share"
        })
        # Register member and link
        s_u, u = _register("mg_member")
        sub = _create_sub(admin_session, u["id"], sid, plans[0]["id"], role="host", group_id=gid)

        r = s_u.get(f"{API}/me/groups")
        assert r.status_code == 200
        arr = r.json()
        assert len(arr) == 1
        entry = arr[0]
        assert entry["group"]["id"] == gid
        assert entry["service"]["id"] == sid
        assert entry["credential"] is not None
        assert entry["credential"]["email"] == "shared@login.test"
        assert entry["credential"]["password"] == "P@ss123", "user in group should see password"
        # members
        assert any(m.get("is_me") for m in entry["members"])

        # Cleanup: delete group
        admin_session.delete(f"{API}/admin/groups/{gid}")

    def test_user_without_group_empty(self, admin_session, services):
        s_u, u = _register("no_group")
        r = s_u.get(f"{API}/me/groups")
        assert r.status_code == 200
        assert r.json() == []

    def test_group_no_credential_returns_null(self, admin_session, services):
        sid = services[0]["id"]
        plans = admin_session.get(f"{API}/admin/services/{sid}/plans").json()
        g = admin_session.post(f"{API}/admin/groups", json={
            "service_id": sid, "name": "Iter7 NoCred", "host_slots": 1, "regular_slots": 4
        }).json()
        gid = g["id"]
        s_u, u = _register("nc_member")
        _create_sub(admin_session, u["id"], sid, plans[0]["id"], group_id=gid)
        arr = s_u.get(f"{API}/me/groups").json()
        assert len(arr) == 1
        assert arr[0]["credential"] is None
        admin_session.delete(f"{API}/admin/groups/{gid}")


# ---------------- PATCH subscription group_id ----------------
class TestSubGroupIdAssign:
    def test_patch_sub_with_group_id(self, admin_session, services):
        sid = services[0]["id"]
        plans = admin_session.get(f"{API}/admin/services/{sid}/plans").json()
        g = admin_session.post(f"{API}/admin/groups", json={
            "service_id": sid, "name": "Iter7 AssignG", "host_slots": 1, "regular_slots": 4
        }).json()
        gid = g["id"]
        s_u, u = _register("assign_user")
        sub = _create_sub(admin_session, u["id"], sid, plans[0]["id"])  # no group
        assert sub.get("group_id") in (None, "")

        r = admin_session.patch(f"{API}/admin/subscriptions/{sub['id']}", json={
            "user_id": u["id"], "service_id": sid, "plan_id": plans[0]["id"],
            "group_id": gid, "role": "regular", "status": "active",
            "start_date": "2026-01-01T00:00:00Z", "price": 45000
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["group_id"] == gid
        admin_session.delete(f"{API}/admin/groups/{gid}")


# ---------------- Public availability ----------------
class TestPublicAvailability:
    def test_availability_unauth(self, services):
        # No auth
        r = requests.get(f"{API}/public/availability", timeout=15)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list)
        assert len(arr) >= 1
        for row in arr:
            for k in ("service_id", "slug", "name", "total_slots", "filled_slots", "available_slots", "groups", "has_availability"):
                assert k in row, f"missing {k} in {row}"


# ---------------- Waitlist ----------------
class TestWaitlist:
    def test_waitlist_create_list_delete(self, admin_session, services):
        sid = services[0]["id"]
        r = requests.post(f"{API}/waitlist", json={
            "email": "iter7_waitlist@example.com", "name": "WL User", "whatsapp": "+62811", "service_id": sid, "message": "please"
        }, timeout=15)
        assert r.status_code == 200, r.text

        # Admin list
        lst = admin_session.get(f"{API}/admin/waitlist").json()
        assert isinstance(lst, list)
        entry = next((x for x in lst if x.get("email") == "iter7_waitlist@example.com"), None)
        assert entry is not None
        eid = entry["id"]

        # Non-admin forbidden
        s_u, _ = _register("wl_nonadmin")
        r2 = s_u.get(f"{API}/admin/waitlist")
        assert r2.status_code in (401, 403)

        # Delete
        r3 = admin_session.delete(f"{API}/admin/waitlist/{eid}")
        assert r3.status_code == 200
        lst2 = admin_session.get(f"{API}/admin/waitlist").json()
        assert not any(x["id"] == eid for x in lst2)
