"""Iter15 backend tests: P1 SEO (sitemap/robots), P3 auto-assign + role validation + unassigned-users."""
import os
import uuid
import requests
import pytest
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@patungandigital.id"
ADMIN_PASSWORD = "Adm!nPd-JavpOaidEa6wZgFnBS"
RUN = uuid.uuid4().hex[:6]


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def user(admin):
    email = f"iter15u_{RUN}@test.com"
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/register", json={"email": email, "password": "userpass123", "name": "Iter15 User"})
    assert r.status_code in (200, 201), r.text
    return s


# ---------------- P1 SEO ----------------
class TestSEO:
    def test_robots_txt(self):
        r = requests.get(f"{BASE}/api/robots.txt")
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")
        body = r.text
        assert "User-agent: *" in body
        assert "Allow: /" in body
        for p in ("/admin", "/dashboard", "/reset-password", "/auth-callback"):
            assert f"Disallow: {p}" in body
        assert "Sitemap:" in body

    def test_sitemap_xml_static_urls(self):
        r = requests.get(f"{BASE}/api/sitemap.xml")
        assert r.status_code == 200
        assert "application/xml" in r.headers.get("content-type", "")
        body = r.text
        assert "<urlset" in body
        assert "<url>" in body
        assert "/about" in body
        assert "/blog" in body

    def test_sitemap_includes_published_post(self, admin):
        slug = f"iter15-seo-{RUN}"
        payload = {"title": f"Iter15 SEO {RUN}", "slug": slug, "content": "hello", "published": True}
        r = admin.post(f"{BASE}/api/admin/blog", json=payload)
        assert r.status_code == 200, r.text
        post_id = r.json()["id"]
        try:
            r2 = requests.get(f"{BASE}/api/sitemap.xml")
            assert slug in r2.text
        finally:
            admin.delete(f"{BASE}/api/admin/blog/{post_id}")


# ---------------- Helpers ----------------
def _get_or_create_service(admin):
    """Return a service id to use. Creates one if none exist."""
    r = admin.get(f"{BASE}/api/admin/services")
    services = r.json()
    if services:
        return services[0]["id"]
    payload = {
        "name": f"Iter15 Svc {RUN}",
        "slug": f"iter15-svc-{RUN}",
        "description": "",
        "price_regular": 10000,
        "price_host": 20000,
        "min_duration_months": 1,
        "active": True,
    }
    r = admin.post(f"{BASE}/api/admin/services", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_service_fresh(admin, name_suffix):
    slug = f"iter15-{name_suffix}-{RUN}"
    payload = {
        "name": f"Iter15 {name_suffix} {RUN}",
        "slug": slug,
        "price_regular": 10000,
        "price_host": 20000,
        "min_duration_months": 1,
        "active": True,
    }
    r = admin.post(f"{BASE}/api/admin/services", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _register(email):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/register", json={"email": email, "password": "pw12345678", "name": email.split("@")[0]})
    assert r.status_code in (200, 201), r.text
    uid = r.json().get("user", {}).get("id") or r.json().get("id")
    return uid, s


def _create_sub(admin, user_id, service_id, role="regular", group_id=None):
    from datetime import datetime, timezone
    payload = {
        "user_id": user_id,
        "service_id": service_id,
        "role": role,
        "start_date": datetime.now(timezone.utc).isoformat(),
        "price": 10000,
        "status": "active",
        "duration_months": 1,
    }
    if group_id:
        payload["group_id"] = group_id
    r = admin.post(f"{BASE}/api/admin/subscriptions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_payment(admin, sub_id, amount=10000):
    r = admin.post(f"{BASE}/api/admin/payments", json={"subscription_id": sub_id, "amount": amount, "duration_months": 1})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mark_paid(admin, payment_id):
    r = admin.patch(f"{BASE}/api/admin/payments/{payment_id}", json={"status": "paid"})
    assert r.status_code == 200, r.text
    return r.json()


def _get_sub(admin, sub_id):
    r = admin.get(f"{BASE}/api/admin/subscriptions")
    for s in r.json():
        if s["id"] == sub_id:
            return s
    return None


# ---------------- P3 Unassigned users ----------------
class TestUnassignedUsers:
    def test_admin_returns_list(self, admin):
        svc_id = _create_service_fresh(admin, "unassigned")
        # Create a user with no sub
        uid, _ = _register(f"iter15un_{RUN}@test.com")
        r = admin.get(f"{BASE}/api/admin/groups/unassigned-users?service_id={svc_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Our new user should appear (no sub, definitely not assigned)
        ids = [u["id"] for u in data]
        assert uid in ids
        me = next(u for u in data if u["id"] == uid)
        for k in ("id", "name", "email", "has_pending_sub", "pending_sub_id", "pending_role"):
            assert k in me
        assert me["has_pending_sub"] is False

    def test_non_admin_forbidden(self, user):
        r = user.get(f"{BASE}/api/admin/groups/unassigned-users?service_id=any")
        assert r.status_code in (401, 403)


# ---------------- P3 Auto-assign ----------------
class TestAutoAssign:
    def test_auto_create_group_and_assign_when_no_group_exists(self, admin):
        svc_id = _create_service_fresh(admin, "autocreate")
        uid, _ = _register(f"iter15ac_{RUN}@test.com")
        sub_id = _create_sub(admin, uid, svc_id, role="regular")
        pay_id = _create_payment(admin, sub_id)
        _mark_paid(admin, pay_id)

        sub = _get_sub(admin, sub_id)
        assert sub is not None
        assert sub.get("group_id"), "sub should be assigned to a group after payment paid"

        # Verify the group is auto_created
        r = admin.get(f"{BASE}/api/admin/groups?service_id={svc_id}")
        groups = r.json()
        assert any(g.get("id") == sub["group_id"] for g in groups)
        chosen = next(g for g in groups if g["id"] == sub["group_id"])
        assert chosen.get("auto_created") is True

    def test_assign_to_existing_group_with_slot(self, admin):
        svc_id = _create_service_fresh(admin, "slotavail")
        # Create a group manually with plenty of slots
        r = admin.post(f"{BASE}/api/admin/groups", json={
            "service_id": svc_id, "name": f"Manual {RUN}",
            "host_slots": 1, "regular_slots": 4, "active": True,
        })
        assert r.status_code == 200
        group_id = r.json()["id"]

        uid, _ = _register(f"iter15slot_{RUN}@test.com")
        sub_id = _create_sub(admin, uid, svc_id, role="regular")
        pay_id = _create_payment(admin, sub_id)
        _mark_paid(admin, pay_id)

        sub = _get_sub(admin, sub_id)
        assert sub.get("group_id") == group_id

    def test_idempotency_no_new_group_on_repeat(self, admin):
        svc_id = _create_service_fresh(admin, "idempot")
        uid, _ = _register(f"iter15idem_{RUN}@test.com")
        sub_id = _create_sub(admin, uid, svc_id, role="regular")
        pay_id = _create_payment(admin, sub_id)
        _mark_paid(admin, pay_id)

        # Count groups before repeat
        g1 = admin.get(f"{BASE}/api/admin/groups?service_id={svc_id}").json()
        # Mark paid again (idempotent via applied_to_sub_at)
        admin.patch(f"{BASE}/api/admin/payments/{pay_id}", json={"status": "paid"})
        g2 = admin.get(f"{BASE}/api/admin/groups?service_id={svc_id}").json()
        assert len(g1) == len(g2), "no additional group should be created on second paid"

        # Sub group_id unchanged
        sub = _get_sub(admin, sub_id)
        assert sub.get("group_id") == g1[0]["id"]


# ---------------- P3 Role validation ----------------
class TestRoleValidation:
    def test_promote_host_conflict_and_resolution(self, admin):
        svc_id = _create_service_fresh(admin, "rolev")
        # Create a group with 2 host slots so we can control easily -- actually 1 host slot is right
        r = admin.post(f"{BASE}/api/admin/groups", json={
            "service_id": svc_id, "name": f"RV {RUN}",
            "host_slots": 1, "regular_slots": 4, "active": True,
        })
        gid = r.json()["id"]

        # Create two users + subs in this group
        uid1, _ = _register(f"iter15rv1_{RUN}@test.com")
        uid2, _ = _register(f"iter15rv2_{RUN}@test.com")
        sub1 = _create_sub(admin, uid1, svc_id, role="regular", group_id=gid)
        sub2 = _create_sub(admin, uid2, svc_id, role="regular", group_id=gid)

        # Promote sub1 to host (should succeed)
        r = admin.patch(f"{BASE}/api/admin/subscriptions/{sub1}", json={"role": "host"})
        assert r.status_code == 200, r.text

        # Try to promote sub2 to host → should 400
        r = admin.patch(f"{BASE}/api/admin/subscriptions/{sub2}", json={"role": "host"})
        assert r.status_code == 400
        assert "Grup ini sudah punya host" in (r.json().get("detail") or "")

        # Demote sub1 → regular
        r = admin.patch(f"{BASE}/api/admin/subscriptions/{sub1}", json={"role": "regular"})
        assert r.status_code == 200

        # Now promote sub2 → should succeed
        r = admin.patch(f"{BASE}/api/admin/subscriptions/{sub2}", json={"role": "host"})
        assert r.status_code == 200
