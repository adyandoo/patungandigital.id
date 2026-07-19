"""Testimonials router — user submits/edits, admin approves, public GET shows approved."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from server import (
    db, now_utc, log_admin_action, get_current_user, require_admin,
    TestimonialInput, TestimonialUpdateInput, TestimonialAdminAction,
)

router = APIRouter()


def _to_public(t: dict, user: Optional[dict] = None) -> dict:
    return {
        "id": str(t["_id"]),
        "rating": t.get("rating"),
        "comment": t.get("comment"),
        "status": t.get("status", "pending"),
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
        "user": {
            "name": (user or {}).get("name") or "Anonim",
            "profile_picture_base64": (user or {}).get("profile_picture_base64"),
            "id": str((user or {}).get("_id", "")),
        } if user else None,
    }


@router.get("/testimonials")
async def public_testimonials(limit: int = Query(default=12, ge=1, le=50)):
    """Public: return approved testimonials with author name + avatar + aggregate rating."""
    approved = await db.testimonials.find({"status": "approved"}).sort("created_at", -1).to_list(limit)
    # Attach users
    user_ids = list({t.get("user_id") for t in approved})
    users = {}
    for uid in user_ids:
        if uid and ObjectId.is_valid(uid):
            u = await db.users.find_one({"_id": ObjectId(uid)})
            if u:
                users[uid] = u
    items = [_to_public(t, users.get(t.get("user_id"))) for t in approved]
    # Aggregate over ALL approved (not just limit)
    agg = await db.testimonials.aggregate([
        {"$match": {"status": "approved"}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    if agg:
        stats = {"avg": round(agg[0]["avg"], 2), "count": agg[0]["count"]}
    else:
        stats = {"avg": 0, "count": 0}
    return {"items": items, "stats": stats}


@router.get("/me/testimonials")
async def my_testimonials(user: dict = Depends(get_current_user)):
    items = await db.testimonials.find({"user_id": user["id"]}).sort("created_at", -1).to_list(None)
    return [_to_public(t, user) for t in items]


@router.post("/me/testimonials")
async def submit_testimonial(input: TestimonialInput, user: dict = Depends(get_current_user)):
    # Require at least one subscription (active or otherwise)
    sub_count = await db.subscriptions.count_documents({"user_id": user["id"]})
    if sub_count == 0:
        raise HTTPException(400, "Kamu harus punya minimal 1 langganan untuk memberi testimoni.")
    doc = {
        "user_id": user["id"],
        "rating": input.rating,
        "comment": input.comment,
        "status": "pending",
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    r = await db.testimonials.insert_one(doc)
    doc["_id"] = r.inserted_id
    return _to_public(doc, user)


@router.patch("/me/testimonials/{tid}")
async def edit_my_testimonial(tid: str, input: TestimonialUpdateInput, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(tid):
        raise HTTPException(400, "Invalid id")
    t = await db.testimonials.find_one({"_id": ObjectId(tid)})
    if not t or t.get("user_id") != user["id"]:
        raise HTTPException(404, "Testimoni tidak ditemukan")
    if t.get("status") == "approved":
        raise HTTPException(400, "Testimoni sudah disetujui admin — tidak bisa diedit. Hapus dan buat baru jika perlu.")
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    updates["updated_at"] = now_utc().isoformat()
    # Editing resets status to pending for admin re-review
    updates["status"] = "pending"
    await db.testimonials.update_one({"_id": t["_id"]}, {"$set": updates})
    t.update(updates)
    return _to_public(t, user)


@router.delete("/me/testimonials/{tid}")
async def delete_my_testimonial(tid: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(tid):
        raise HTTPException(400, "Invalid id")
    t = await db.testimonials.find_one({"_id": ObjectId(tid)})
    if not t or t.get("user_id") != user["id"]:
        raise HTTPException(404, "Testimoni tidak ditemukan")
    if t.get("status") == "approved":
        # Allow delete even if approved — user retracting their public testimonial is a valid right
        pass
    await db.testimonials.delete_one({"_id": t["_id"]})
    return {"ok": True}


# --------- Admin --------- #
@router.get("/admin/testimonials")
async def admin_list_testimonials(status: Optional[str] = None, admin: dict = Depends(require_admin)):
    q = {}
    if status in {"pending", "approved", "rejected"}:
        q["status"] = status
    items = await db.testimonials.find(q).sort("created_at", -1).to_list(None)
    out = []
    for t in items:
        uid = t.get("user_id")
        u = None
        if uid and ObjectId.is_valid(uid):
            u = await db.users.find_one({"_id": ObjectId(uid)})
        out.append(_to_public(t, u))
    return out


@router.patch("/admin/testimonials/{tid}")
async def admin_update_testimonial(tid: str, input: TestimonialAdminAction, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(tid):
        raise HTTPException(400, "Invalid id")
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Tidak ada field untuk diupdate")
    if "status" in updates and updates["status"] not in {"pending", "approved", "rejected"}:
        raise HTTPException(422, "status invalid")
    updates["updated_at"] = now_utc().isoformat()
    r = await db.testimonials.update_one({"_id": ObjectId(tid)}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Testimoni tidak ditemukan")
    await log_admin_action(admin, "update_testimonial", f"testimonial:{tid}", updates)
    t = await db.testimonials.find_one({"_id": ObjectId(tid)})
    u = await db.users.find_one({"_id": ObjectId(t["user_id"])}) if ObjectId.is_valid(t.get("user_id", "")) else None
    return _to_public(t, u)


@router.delete("/admin/testimonials/{tid}")
async def admin_delete_testimonial(tid: str, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(tid):
        raise HTTPException(400, "Invalid id")
    r = await db.testimonials.delete_one({"_id": ObjectId(tid)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Testimoni tidak ditemukan")
    await log_admin_action(admin, "delete_testimonial", f"testimonial:{tid}", {})
    return {"ok": True}
