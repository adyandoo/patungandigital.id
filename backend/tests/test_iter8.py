"""Iter8 tests: router extraction regression, waitlist status PATCH,
group status/expires_at, suggest endpoint, H-7 scheduler, E2E netflix flow."""
import os
import time
from datetime import datetime, timedelta, timezone
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@patungandigital.id", "password": "admin123"}
PREFIX = "Iter8"


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


@pytest.fixture(scope="module")
def netflix_service(services):
    n = next((s for s in services if s["slug"] == "netflix"), None)
    assert n, "netflix service missing"
    return n


def _register(tag):
    ts = int(time.time() * 1000000)
    email = f"iter8_{tag}_{ts}@example.com"
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={
        "name": f"{PREFIX} {tag}", "email": email, "password": "pass1234", "whatsapp": "+628111222333"
    }, timeout=15)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me").json()
    return s, me


# ============== Regression: routers/groups endpoints still work ==============
class TestRouterExtraction:
    def test_admin_list_groups_works(self, admin_session):
        r = admin_session.get(f"{API}/admin/groups", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_public_availability_works(self):
        r = requests.get(f"{API}/public/availability", timeout=15)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        if arr:
            e = arr[0]
            for k in ("service_id", "slug", "total_slots", "filled_slots", "has_availability"):
                assert k in e

    def test_waitlist_post_no_auth(self, netflix_service):
        r = requests.post(f"{API}/waitlist", json={
            "service_id": netflix_service["id"], "email": f"iter8_wl_{int(time.time()*1000)}@example.com",
            "name": "WL Iter8"
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_admin_waitlist_list_gated(self):
        r = requests.get(f"{API}/admin/waitlist", timeout=15)
        assert r.status_code in (401, 403)


# ============== Group status + expires_at ==============
class TestGroupStatusExpires:
    def test_create_with_status_and_expires(self, admin_session, netflix_service):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        r = admin_session.post(f"{API}/admin/groups", json={
            "service_id": netflix_service["id"], "name": f"{PREFIX}_grp_status_{int(time.time())}",
            "host_slots": 1, "regular_slots": 4, "active": True,
            "status": "paused", "expires_at": expires
        }, timeout=15)
        assert r.status_code == 200, r.text
        g = r.json()
        assert g.get("status") == "paused"
        assert g.get("expires_at") is not None

        # PATCH to active + new expires_at
        new_exp = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        r2 = admin_session.patch(f"{API}/admin/groups/{g['id']}", json={
            "status": "active", "expires_at": new_exp
        }, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("status") == "active"
        # cleanup
        admin_session.delete(f"{API}/admin/groups/{g['id']}", timeout=15)


# ============== Suggest endpoint ==============
class TestSuggest:
    def test_suggest_returns_available_groups(self, admin_session, netflix_service):
        # Create a group with 4 regular slots
        r = admin_session.post(f"{API}/admin/groups", json={
            "service_id": netflix_service["id"], "name": f"{PREFIX}_sug_{int(time.time())}",
            "host_slots": 1, "regular_slots": 4, "active": True, "status": "active"
        }, timeout=15)
        gid = r.json()["id"]
        try:
            s = admin_session.get(f"{API}/admin/groups/suggest", params={
                "service_id": netflix_service["id"], "role": "regular"
            }, timeout=15)
            assert s.status_code == 200, s.text
            arr = s.json()
            ids = [x["id"] for x in arr]
            assert gid in ids
            entry = next(x for x in arr if x["id"] == gid)
            assert entry["available_for_role"] == 4
            assert entry["filled_regular"] == 0
        finally:
            admin_session.delete(f"{API}/admin/groups/{gid}", timeout=15)

    def test_suggest_excludes_paused(self, admin_session, netflix_service):
        r = admin_session.post(f"{API}/admin/groups", json={
            "service_id": netflix_service["id"], "name": f"{PREFIX}_paused_{int(time.time())}",
            "host_slots": 1, "regular_slots": 4, "active": True, "status": "paused"
        }, timeout=15)
        gid = r.json()["id"]
        try:
            s = admin_session.get(f"{API}/admin/groups/suggest", params={
                "service_id": netflix_service["id"], "role": "regular"
            }, timeout=15)
            assert s.status_code == 200
            ids = [x["id"] for x in s.json()]
            assert gid not in ids
        finally:
            admin_session.delete(f"{API}/admin/groups/{gid}", timeout=15)


# ============== Waitlist status PATCH ==============
class TestWaitlistStatus:
    def test_patch_status_contacted(self, admin_session, netflix_service):
        # create waitlist entry
        r = requests.post(f"{API}/waitlist", json={
            "service_id": netflix_service["id"],
            "email": f"iter8_wl_status_{int(time.time()*1000)}@example.com",
            "name": "WL Status"
        }, timeout=15)
        assert r.status_code == 200
        # list to find id
        lst = admin_session.get(f"{API}/admin/waitlist", timeout=15).json()
        entry = next((e for e in lst if e.get("name") == "WL Status"), None)
        assert entry is not None
        eid = entry["id"]
        assert entry.get("status") == "new"
        # patch
        p = admin_session.patch(f"{API}/admin/waitlist/{eid}", json={"status": "contacted"}, timeout=15)
        assert p.status_code == 200, p.text
        assert p.json().get("status") == "contacted"
        # verify via list
        lst2 = admin_session.get(f"{API}/admin/waitlist", timeout=15).json()
        e2 = next(e for e in lst2 if e["id"] == eid)
        assert e2["status"] == "contacted"
        # cleanup
        admin_session.delete(f"{API}/admin/waitlist/{eid}", timeout=15)


# ============== H-7 scheduler ==============
class TestSchedulerH7:
    def test_h7_reminder_marks_and_logs_idempotent(self, admin_session, netflix_service):
        expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        r = admin_session.post(f"{API}/admin/groups", json={
            "service_id": netflix_service["id"], "name": f"{PREFIX}_h7_{int(time.time())}",
            "host_slots": 1, "regular_slots": 4, "active": True,
            "status": "active", "expires_at": expires
        }, timeout=15)
        assert r.status_code == 200, r.text
        gid = r.json()["id"]
        try:
            # Run scheduler
            run1 = admin_session.post(f"{API}/admin/scheduler/run-now", timeout=30)
            assert run1.status_code == 200, run1.text
            data1 = run1.json()
            assert data1.get("expiring_groups", 0) >= 1

            # Verify group flag set
            lst = admin_session.get(f"{API}/admin/groups", timeout=15).json()
            g = next((x for x in lst if x["id"] == gid), None)
            assert g is not None
            assert g.get("expiry_reminder_sent") is True

            # Second run — should NOT re-count (idempotent)
            run2 = admin_session.post(f"{API}/admin/scheduler/run-now", timeout=30)
            assert run2.status_code == 200
            data2 = run2.json()
            # Not counted again because flag is set
            # (accept 0 or fewer than data1)
            assert data2.get("expiring_groups", 0) < data1.get("expiring_groups", 999)
        finally:
            admin_session.delete(f"{API}/admin/groups/{gid}", timeout=15)


# ============== E2E: Netflix group with 2 users ==============
class TestE2ENetflixFlow:
    def test_full_flow(self, admin_session, netflix_service):
        # Plans
        plans = admin_session.get(f"{API}/admin/services/{netflix_service['id']}/plans", timeout=15).json()
        assert plans, "no plans"
        plan_id = plans[0]["id"]

        # Create group
        r = admin_session.post(f"{API}/admin/groups", json={
            "service_id": netflix_service["id"], "name": f"{PREFIX}_Netflix_A_{int(time.time())}",
            "host_slots": 1, "regular_slots": 4, "active": True, "status": "active"
        }, timeout=15)
        assert r.status_code == 200
        gid = r.json()["id"]

        try:
            # Register 2 users
            host_sess, host_me = _register("host")
            reg_sess, reg_me = _register("reg")

            # Create subs
            host_body = {"user_id": host_me["id"], "service_id": netflix_service["id"],
                         "plan_id": plan_id, "role": "host", "status": "active",
                         "start_date": "2026-01-01T00:00:00Z", "price": 0}
            reg_body = {**host_body, "user_id": reg_me["id"], "role": "regular", "price": 45000}
            hs = admin_session.post(f"{API}/admin/subscriptions", json=host_body, timeout=15)
            rs = admin_session.post(f"{API}/admin/subscriptions", json=reg_body, timeout=15)
            assert hs.status_code == 200, hs.text
            assert rs.status_code == 200, rs.text
            hs_id, rs_id = hs.json()["id"], rs.json()["id"]

            # Assign group_id to both (PATCH requires full body — known iter7 note)
            for sid, body in ((hs_id, host_body), (rs_id, reg_body)):
                pr = admin_session.patch(f"{API}/admin/subscriptions/{sid}", json={**body, "group_id": gid}, timeout=15)
                assert pr.status_code == 200, pr.text

            # Set credential
            cr = admin_session.put(f"{API}/admin/groups/{gid}/credential", json={
                "email": "shared@netflix.com", "password": "sh4red", "notes": "Profile Guest"
            }, timeout=15)
            assert cr.status_code == 200

            # Fetch /me/groups as reg
            mg = reg_sess.get(f"{API}/me/groups", timeout=15).json()
            assert len(mg) == 1
            entry = mg[0]
            assert entry["group"]["name"].startswith(f"{PREFIX}_Netflix_A")
            assert entry["role"] == "regular"
            assert entry["credential"]["email"] == "shared@netflix.com"
            assert entry["credential"]["password"] == "sh4red"
            assert len(entry["members"]) == 2
            me_rows = [m for m in entry["members"] if m.get("is_me")]
            assert len(me_rows) == 1
            assert me_rows[0]["role"] == "regular"

            # Fetch as host
            hg = host_sess.get(f"{API}/me/groups", timeout=15).json()
            assert len(hg) == 1
            assert hg[0]["credential"]["password"] == "sh4red"
            assert hg[0]["role"] == "host"

            # Cleanup subs
            admin_session.delete(f"{API}/admin/subscriptions/{hs_id}", timeout=15)
            admin_session.delete(f"{API}/admin/subscriptions/{rs_id}", timeout=15)
        finally:
            admin_session.delete(f"{API}/admin/groups/{gid}", timeout=15)


@pytest.fixture(scope="session", autouse=True)
def cleanup_at_end():
    yield
    # cleanup test users
    try:
        s = requests.Session()
        s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        s.post(f"{API}/admin/cleanup-test-users", params={"prefix": "iter8"}, timeout=30)
    except Exception:
        pass
