"""CMS router: About page, Blog posts, Announcements, SEO."""
import re
import unicodedata
import os
from datetime import datetime, timezone
from typing import Optional, List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from server import (
    db, now_utc, log_admin_action, get_current_user, require_admin,
    AboutInput, BlogPostInput, BlogPostUpdate, AnnouncementInput, AnnouncementUpdate,
)

router = APIRouter()


# ---------------- SEO: sitemap.xml + robots.txt ---------------- #
@router.get("/sitemap.xml")
async def sitemap_xml():
    """Dynamic sitemap listing homepage, /about, /blog, and each published blog post."""
    base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    now_iso = now_utc().strftime("%Y-%m-%d")
    urls = [
        {"loc": f"{base}/", "changefreq": "weekly", "priority": "1.0", "lastmod": now_iso},
        {"loc": f"{base}/about", "changefreq": "monthly", "priority": "0.8", "lastmod": now_iso},
        {"loc": f"{base}/blog", "changefreq": "daily", "priority": "0.9", "lastmod": now_iso},
    ]
    posts = await db.blog_posts.find({"published": True}, {"slug": 1, "updated_at": 1, "published_at": 1}).to_list(None)
    for p in posts:
        lastmod = p.get("updated_at") or p.get("published_at") or now_iso
        if isinstance(lastmod, str) and "T" in lastmod:
            lastmod = lastmod.split("T")[0]
        urls.append({
            "loc": f"{base}/blog/{p['slug']}",
            "changefreq": "monthly",
            "priority": "0.7",
            "lastmod": lastmod,
        })
    xml_items = "\n".join(
        f"  <url><loc>{u['loc']}</loc><lastmod>{u['lastmod']}</lastmod>"
        f"<changefreq>{u['changefreq']}</changefreq><priority>{u['priority']}</priority></url>"
        for u in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{xml_items}\n</urlset>'
    return Response(content=xml, media_type="application/xml")


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /dashboard
Disallow: /reset-password
Disallow: /auth-callback

Sitemap: {base}/api/sitemap.xml
"""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "post"


DEFAULT_ABOUT = {
    "hero_title": "Tentang patungandigital.id",
    "story": "Kami membantu keluarga, teman, dan komunitas patungan langganan digital premium secara aman, legal, dan hemat. Semua diatur oleh admin — dari mencari anggota, menyalurkan akses, sampai mengingatkan pembayaran.",
    "mission": "Membuat akses konten premium terjangkau untuk semua, tanpa ribet.",
    "contact_email": "halo@patungandigital.id",
    "contact_whatsapp": "",
    "contact_address": "",
}


# ---------------- About ---------------- #
@router.get("/about")
async def get_about_public():
    cfg = await db.settings.find_one({"key": "about_page"}) or {}
    data = {**DEFAULT_ABOUT}
    for k in ("hero_title", "story", "mission", "contact_email", "contact_whatsapp", "contact_address"):
        if cfg.get(k) is not None:
            data[k] = cfg.get(k)
    data["updated_at"] = cfg.get("updated_at")
    return data


@router.put("/admin/about")
async def set_about(input: AboutInput, admin: dict = Depends(require_admin)):
    payload = input.model_dump()
    payload["key"] = "about_page"
    payload["updated_at"] = now_utc().isoformat()
    await db.settings.update_one({"key": "about_page"}, {"$set": payload}, upsert=True)
    await log_admin_action(admin, "update_about_page", "settings", {"hero_title": payload["hero_title"]})
    return {"ok": True}


# ---------------- Blog ---------------- #
def _blog_to_public(p: dict) -> dict:
    return {
        "id": str(p["_id"]),
        "title": p.get("title"),
        "slug": p.get("slug"),
        "excerpt": p.get("excerpt", ""),
        "content": p.get("content", ""),
        "cover_image_base64": p.get("cover_image_base64"),
        "tags": p.get("tags", []),
        "published": p.get("published", False),
        "published_at": p.get("published_at"),
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
        "author_name": p.get("author_name"),
    }


@router.get("/blog")
async def list_blog_public(
    tag: Optional[str] = None,
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    q = {"published": True}
    if tag:
        q["tags"] = tag
    total = await db.blog_posts.count_documents(q)
    items = await db.blog_posts.find(q).sort("published_at", -1).skip(offset).limit(limit).to_list(limit)
    # Compute tag cloud from all published posts (unpaginated)
    tags_agg = await db.blog_posts.aggregate([
        {"$match": {"published": True}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 30},
    ]).to_list(30)
    return {
        "items": [_blog_to_public(p) for p in items],
        "total": total,
        "tags": [{"tag": t["_id"], "count": t["count"]} for t in tags_agg],
    }


@router.get("/blog/{slug}")
async def get_blog_post_public(slug: str):
    p = await db.blog_posts.find_one({"slug": slug, "published": True})
    if not p:
        raise HTTPException(404, "Post tidak ditemukan")
    return _blog_to_public(p)


@router.get("/admin/blog")
async def admin_list_blog(admin: dict = Depends(require_admin)):
    items = await db.blog_posts.find({}).sort("created_at", -1).to_list(None)
    return [_blog_to_public(p) for p in items]


@router.post("/admin/blog")
async def admin_create_blog(input: BlogPostInput, admin: dict = Depends(require_admin)):
    slug = input.slug or slugify(input.title)
    # Ensure uniqueness
    if await db.blog_posts.find_one({"slug": slug}):
        slug = f"{slug}-{int(now_utc().timestamp())}"
    now = now_utc()
    doc = input.model_dump()
    doc["slug"] = slug
    doc["tags"] = [t.strip().lower() for t in (doc.get("tags") or []) if t and t.strip()]
    doc["author_id"] = admin["id"]
    doc["author_name"] = admin.get("name") or "Admin"
    doc["created_at"] = now.isoformat()
    doc["updated_at"] = now.isoformat()
    doc["published_at"] = now.isoformat() if input.published else None
    r = await db.blog_posts.insert_one(doc)
    doc["_id"] = r.inserted_id
    await log_admin_action(admin, "create_blog_post", f"blog:{r.inserted_id}", {"title": input.title, "slug": slug})
    return _blog_to_public(doc)


@router.patch("/admin/blog/{post_id}")
async def admin_update_blog(post_id: str, input: BlogPostUpdate, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(400, "Invalid id")
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Tidak ada field untuk diupdate")
    if "tags" in updates:
        updates["tags"] = [t.strip().lower() for t in updates["tags"] if t and t.strip()]
    updates["updated_at"] = now_utc().isoformat()
    # If publishing for first time, stamp published_at
    if updates.get("published") is True:
        existing = await db.blog_posts.find_one({"_id": ObjectId(post_id)}, {"published_at": 1})
        if existing and not existing.get("published_at"):
            updates["published_at"] = now_utc().isoformat()
    # If slug provided and differs, ensure unique
    if updates.get("slug"):
        conflict = await db.blog_posts.find_one({"slug": updates["slug"], "_id": {"$ne": ObjectId(post_id)}})
        if conflict:
            raise HTTPException(400, "Slug sudah dipakai")
    r = await db.blog_posts.update_one({"_id": ObjectId(post_id)}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Post tidak ditemukan")
    await log_admin_action(admin, "update_blog_post", f"blog:{post_id}", {k: (v if k != "content" else "<len>") for k, v in updates.items()})
    p = await db.blog_posts.find_one({"_id": ObjectId(post_id)})
    return _blog_to_public(p)


@router.delete("/admin/blog/{post_id}")
async def admin_delete_blog(post_id: str, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(400, "Invalid id")
    r = await db.blog_posts.delete_one({"_id": ObjectId(post_id)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Post tidak ditemukan")
    await log_admin_action(admin, "delete_blog_post", f"blog:{post_id}", {})
    return {"ok": True}


# ---------------- Announcements ---------------- #
def _ann_to_public(a: dict, user_id: Optional[str] = None) -> dict:
    return {
        "id": str(a["_id"]),
        "title": a.get("title"),
        "body": a.get("body"),
        "target": a.get("target", "all"),
        "service_ids": a.get("service_ids", []),
        "severity": a.get("severity", "info"),
        "expires_at": (a["expires_at"].isoformat() if isinstance(a.get("expires_at"), datetime) else a.get("expires_at")),
        "created_at": a.get("created_at"),
        "dismissed": bool(user_id and user_id in (a.get("dismissed_by") or [])),
    }


async def _active_announcements_for_user(user: dict) -> list:
    now = now_utc()
    # Fetch user's active service_ids
    subs = await db.subscriptions.find({"user_id": user["id"], "status": "active"}).to_list(None)
    user_service_ids = list({s.get("service_id") for s in subs if s.get("service_id")})
    q = {
        "$and": [
            {"$or": [{"expires_at": None}, {"expires_at": {"$exists": False}}, {"expires_at": {"$gt": now}}]},
            {"$or": [
                {"target": "all"},
                {"$and": [{"target": "service_ids"}, {"service_ids": {"$in": user_service_ids}}]},
            ]},
        ]
    }
    items = await db.announcements.find(q).sort("created_at", -1).to_list(None)
    return items


@router.get("/me/announcements")
async def me_announcements(only_active: bool = True, user: dict = Depends(get_current_user)):
    items = await _active_announcements_for_user(user)
    if only_active:
        items = [a for a in items if user["id"] not in (a.get("dismissed_by") or [])]
    return [_ann_to_public(a, user_id=user["id"]) for a in items]


@router.post("/me/announcements/{ann_id}/dismiss")
async def dismiss_announcement(ann_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(ann_id):
        raise HTTPException(400, "Invalid id")
    r = await db.announcements.update_one(
        {"_id": ObjectId(ann_id)},
        {"$addToSet": {"dismissed_by": user["id"]}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Pengumuman tidak ditemukan")
    return {"ok": True}


@router.get("/admin/announcements")
async def admin_list_announcements(admin: dict = Depends(require_admin)):
    items = await db.announcements.find({}).sort("created_at", -1).to_list(None)
    return [{**_ann_to_public(a), "dismissed_by_count": len(a.get("dismissed_by") or [])} for a in items]


@router.post("/admin/announcements")
async def admin_create_announcement(input: AnnouncementInput, admin: dict = Depends(require_admin)):
    if input.target not in {"all", "service_ids"}:
        raise HTTPException(422, "target must be 'all' or 'service_ids'")
    if input.severity not in {"info", "warning", "critical"}:
        raise HTTPException(422, "severity must be info|warning|critical")
    doc = input.model_dump()
    if input.target == "all":
        doc["service_ids"] = []
    doc["created_at"] = now_utc().isoformat()
    doc["created_by"] = admin["id"]
    doc["dismissed_by"] = []
    r = await db.announcements.insert_one(doc)
    doc["_id"] = r.inserted_id
    await log_admin_action(admin, "create_announcement", f"announcement:{r.inserted_id}", {"title": input.title, "target": input.target})
    return _ann_to_public(doc)


@router.patch("/admin/announcements/{ann_id}")
async def admin_update_announcement(ann_id: str, input: AnnouncementUpdate, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(ann_id):
        raise HTTPException(400, "Invalid id")
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Tidak ada field untuk diupdate")
    r = await db.announcements.update_one({"_id": ObjectId(ann_id)}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Pengumuman tidak ditemukan")
    await log_admin_action(admin, "update_announcement", f"announcement:{ann_id}", updates)
    a = await db.announcements.find_one({"_id": ObjectId(ann_id)})
    return _ann_to_public(a)


@router.delete("/admin/announcements/{ann_id}")
async def admin_delete_announcement(ann_id: str, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(ann_id):
        raise HTTPException(400, "Invalid id")
    r = await db.announcements.delete_one({"_id": ObjectId(ann_id)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Pengumuman tidak ditemukan")
    await log_admin_action(admin, "delete_announcement", f"announcement:{ann_id}", {})
    return {"ok": True}
