"""Iter14 backend tests: P3 rate-limit, P4 About, P5 Blog, P6 Announcements."""
import os
import time
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
    email = f"iter14u_{RUN}@test.com"
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/register", json={"email": email, "password": "userpass123", "name": "Iter14 User"})
    assert r.status_code in (200, 201), r.text
    s._email = email
    s._id = r.json().get("user", {}).get("id") or r.json().get("id")
    return s


# ---------- P3 rate-limit ----------
class TestForgotPasswordRateLimit:
    def test_first_call_ok(self, admin):
        email = f"iter14rl_{RUN}@test.com"
        # First register user so an actual token can be inserted
        r = requests.post(f"{BASE}/api/auth/register", json={"email": email, "password": "pw12345678", "name": "RL"})
        assert r.status_code in (200, 201)
        r1 = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": email})
        assert r1.status_code == 200
        assert r1.json().get("rate_limited") is not True

        r2 = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": email})
        assert r2.status_code == 200
        assert r2.json().get("rate_limited") is True


# ---------- P4 About ----------
class TestAbout:
    def test_public_defaults(self):
        r = requests.get(f"{BASE}/api/about")
        assert r.status_code == 200
        d = r.json()
        for k in ("hero_title", "story", "mission", "contact_email"):
            assert k in d

    def test_admin_put_persists(self, admin):
        new_title = f"Tentang iter14 {RUN}"
        story = f"Story iter14 run {RUN}"
        payload = {"hero_title": new_title, "story": story, "mission": "M", "contact_email": "x@y.com"}
        r = admin.put(f"{BASE}/api/admin/about", json=payload)
        assert r.status_code == 200, r.text

        r2 = requests.get(f"{BASE}/api/about")
        d = r2.json()
        assert d["hero_title"] == new_title
        assert d["story"] == story

    def test_non_admin_forbidden(self, user):
        r = user.put(f"{BASE}/api/admin/about", json={"hero_title": "x", "story": "y"})
        assert r.status_code in (401, 403)


# ---------- P5 Blog ----------
blog_state = {}


class TestBlog:
    def test_create_draft_and_public_hidden(self, admin):
        slug = f"iter14-post-{RUN}"
        payload = {"title": f"Iter14 Post {RUN}", "slug": slug, "content": "# Hello\n\nBody", "tags": ["tips", "iter14"], "published": False, "excerpt": "e"}
        r = admin.post(f"{BASE}/api/admin/blog", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slug"] == slug
        assert d["published"] is False
        blog_state["id"] = d["id"]
        blog_state["slug"] = slug

        # Public list should not include draft
        r2 = requests.get(f"{BASE}/api/blog")
        ids = [x["id"] for x in r2.json()["items"]]
        assert blog_state["id"] not in ids

        # Public detail should 404
        r3 = requests.get(f"{BASE}/api/blog/{slug}")
        assert r3.status_code == 404

    def test_publish_and_appears(self, admin):
        r = admin.patch(f"{BASE}/api/admin/blog/{blog_state['id']}", json={"published": True})
        assert r.status_code == 200
        assert r.json()["published"] is True

        r2 = requests.get(f"{BASE}/api/blog")
        ids = [x["id"] for x in r2.json()["items"]]
        assert blog_state["id"] in ids

        r3 = requests.get(f"{BASE}/api/blog/{blog_state['slug']}")
        assert r3.status_code == 200
        assert r3.json()["content"].startswith("# Hello")

    def test_duplicate_slug_suffix_on_create(self, admin):
        # POST same slug -> suffix added
        payload = {"title": "Another", "slug": blog_state["slug"], "content": "x", "published": False}
        r = admin.post(f"{BASE}/api/admin/blog", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["slug"].startswith(blog_state["slug"] + "-")
        blog_state["id2"] = d["id"]

    def test_duplicate_slug_patch_400(self, admin):
        r = admin.patch(f"{BASE}/api/admin/blog/{blog_state['id2']}", json={"slug": blog_state["slug"]})
        assert r.status_code == 400

    def test_tag_filter_and_ranking(self, admin):
        r = requests.get(f"{BASE}/api/blog", params={"tag": "tips"})
        assert r.status_code == 200
        d = r.json()
        assert any(x["id"] == blog_state["id"] for x in d["items"])
        assert isinstance(d.get("tags"), list)

    def test_excerpt_too_long_422(self, admin):
        r = admin.post(f"{BASE}/api/admin/blog", json={"title": "T", "content": "c", "excerpt": "x" * 301})
        assert r.status_code == 422

    def test_empty_title_422(self, admin):
        r = admin.post(f"{BASE}/api/admin/blog", json={"title": "", "content": "c"})
        assert r.status_code == 422

    def test_non_admin_protected(self, user):
        r = user.post(f"{BASE}/api/admin/blog", json={"title": "x", "content": "y"})
        assert r.status_code in (401, 403)
        r2 = user.get(f"{BASE}/api/admin/blog")
        assert r2.status_code in (401, 403)

    def test_delete(self, admin):
        r = admin.delete(f"{BASE}/api/admin/blog/{blog_state['id2']}")
        assert r.status_code == 200
        # Cleanup main post too
        admin.delete(f"{BASE}/api/admin/blog/{blog_state['id']}")


# ---------- P6 Announcements ----------
ann_state = {}


class TestAnnouncements:
    def test_create_all_and_user_sees(self, admin, user):
        r = admin.post(f"{BASE}/api/admin/announcements", json={
            "title": f"All iter14 {RUN}", "body": "Hi all", "target": "all", "severity": "info"
        })
        assert r.status_code == 200, r.text
        ann_state["all_id"] = r.json()["id"]

        r2 = user.get(f"{BASE}/api/me/announcements")
        assert r2.status_code == 200
        ids = [a["id"] for a in r2.json()]
        assert ann_state["all_id"] in ids

    def test_severity_invalid_422(self, admin):
        r = admin.post(f"{BASE}/api/admin/announcements", json={
            "title": "x", "body": "y", "target": "all", "severity": "invalid"
        })
        assert r.status_code == 422

    def test_target_invalid_422(self, admin):
        r = admin.post(f"{BASE}/api/admin/announcements", json={
            "title": "x", "body": "y", "target": "invalid", "severity": "info"
        })
        assert r.status_code == 422

    def test_service_scoped_not_seen_by_unsubscribed_user(self, admin, user):
        # Fetch a service id
        rs = admin.get(f"{BASE}/api/admin/services")
        services = rs.json()
        if not services:
            pytest.skip("no services")
        svc_id = services[0]["id"]

        r = admin.post(f"{BASE}/api/admin/announcements", json={
            "title": f"Scoped {RUN}", "body": "only subs", "target": "service_ids",
            "service_ids": [svc_id], "severity": "warning"
        })
        assert r.status_code == 200
        ann_state["scoped_id"] = r.json()["id"]

        r2 = user.get(f"{BASE}/api/me/announcements")
        ids = [a["id"] for a in r2.json()]
        assert ann_state["scoped_id"] not in ids  # user has no subscription

    def test_dismiss_removes_from_only_active(self, admin, user):
        r = user.post(f"{BASE}/api/me/announcements/{ann_state['all_id']}/dismiss")
        assert r.status_code == 200

        r2 = user.get(f"{BASE}/api/me/announcements", params={"only_active": "true"})
        ids = [a["id"] for a in r2.json()]
        assert ann_state["all_id"] not in ids

        r3 = user.get(f"{BASE}/api/me/announcements", params={"only_active": "false"})
        items = r3.json()
        found = [a for a in items if a["id"] == ann_state["all_id"]]
        assert found and found[0].get("dismissed") is True

    def test_expired_not_returned(self, admin, user):
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        r = admin.post(f"{BASE}/api/admin/announcements", json={
            "title": f"Expired {RUN}", "body": "old", "target": "all", "severity": "info", "expires_at": past
        })
        assert r.status_code == 200
        ex_id = r.json()["id"]
        ann_state["expired_id"] = ex_id
        r2 = user.get(f"{BASE}/api/me/announcements")
        ids = [a["id"] for a in r2.json()]
        assert ex_id not in ids

        r3 = admin.get(f"{BASE}/api/admin/announcements")
        admin_ids = [a["id"] for a in r3.json()]
        assert ex_id in admin_ids
        # dismissed_by_count present
        assert all("dismissed_by_count" in a for a in r3.json())

    def test_cleanup(self, admin):
        for k in ("all_id", "scoped_id", "expired_id"):
            aid = ann_state.get(k)
            if aid:
                admin.delete(f"{BASE}/api/admin/announcements/{aid}")
