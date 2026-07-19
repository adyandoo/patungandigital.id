"""Groups + Waitlist router — split from server.py."""
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends

from server import (
    db, now_utc, oid, log_admin_action,
    get_current_user, require_admin,
    GroupInput, CredentialInput, WaitlistInput,
)

router = APIRouter()


# ---------------- Admin: Groups ---------------- #
@router.get("/admin/groups")
async def admin_list_groups(admin: dict = Depends(require_admin), service_id: Optional[str] = None):
    q = {"service_id": service_id} if service_id else {}
    groups = await db.groups.find(q).to_list(None)
    for g in groups:
        g["id"] = oid(g.pop("_id"))
        subs = await db.subscriptions.find({"group_id": g["id"]}).to_list(None)
        members = []
        for s in subs:
            u = await db.users.find_one({"_id": ObjectId(s["user_id"])}) if ObjectId.is_valid(s["user_id"]) else None
            members.append({"subscription_id": str(s["_id"]), "user_id": s["user_id"], "role": s.get("role"),
                            "name": (u or {}).get("name"), "email": (u or {}).get("email"), "status": s.get("status")})
        g["members"] = members
        g["filled_host"] = sum(1 for m in members if m["role"] == "host" and m["status"] == "active")
        g["filled_regular"] = sum(1 for m in members if m["role"] == "regular" and m["status"] == "active")
        cred = await db.group_credentials.find_one({"group_id": g["id"]}, {"password": 0})
        if cred:
            cred["id"] = oid(cred.pop("_id"))
        g["credential"] = cred
    return groups


@router.post("/admin/groups")
async def admin_create_group(input: GroupInput, admin: dict = Depends(require_admin)):
    doc = input.model_dump()
    doc.setdefault("status", "active")
    doc["created_at"] = now_utc().isoformat()
    result = await db.groups.insert_one(doc)
    doc["id"] = oid(result.inserted_id)
    doc.pop("_id", None)
    await log_admin_action(admin, "create_group", f"group:{doc['id']}", {"name": input.name, "service_id": input.service_id})
    return doc


@router.patch("/admin/groups/{group_id}")
async def admin_update_group(group_id: str, body: dict, admin: dict = Depends(require_admin)):
    allowed = {k: v for k, v in body.items() if k in {"name", "host_slots", "regular_slots", "notes", "active", "status", "service_id", "expires_at"}}
    if allowed:
        await db.groups.update_one({"_id": ObjectId(group_id)}, {"$set": allowed})
    g = await db.groups.find_one({"_id": ObjectId(group_id)})
    g["id"] = oid(g.pop("_id"))
    return g


@router.delete("/admin/groups/{group_id}")
async def admin_delete_group(group_id: str, admin: dict = Depends(require_admin)):
    await db.groups.delete_one({"_id": ObjectId(group_id)})
    await db.group_credentials.delete_many({"group_id": group_id})
    await db.subscriptions.update_many({"group_id": group_id}, {"$set": {"group_id": None}})
    await log_admin_action(admin, "delete_group", f"group:{group_id}")
    return {"ok": True}


# ---------------- Group credentials ---------------- #
@router.get("/admin/groups/{group_id}/credential")
async def admin_get_credential(group_id: str, admin: dict = Depends(require_admin)):
    c = await db.group_credentials.find_one({"group_id": group_id})
    if not c:
        return None
    c["id"] = oid(c.pop("_id"))
    return c


@router.put("/admin/groups/{group_id}/credential")
async def admin_set_credential(group_id: str, input: CredentialInput, admin: dict = Depends(require_admin)):
    doc = {**input.model_dump(), "group_id": group_id, "updated_at": now_utc().isoformat()}
    await db.group_credentials.update_one({"group_id": group_id}, {"$set": doc}, upsert=True)
    await log_admin_action(admin, "set_group_credential", f"group:{group_id}", {"email": input.email})
    c = await db.group_credentials.find_one({"group_id": group_id})
    c["id"] = oid(c.pop("_id"))
    return c


@router.delete("/admin/groups/{group_id}/credential")
async def admin_delete_credential(group_id: str, admin: dict = Depends(require_admin)):
    await db.group_credentials.delete_one({"group_id": group_id})
    await log_admin_action(admin, "delete_group_credential", f"group:{group_id}")
    return {"ok": True}


# ---------------- User: My groups ---------------- #
@router.get("/me/groups")
async def my_groups(user: dict = Depends(get_current_user)):
    subs = await db.subscriptions.find({"user_id": user["id"], "group_id": {"$ne": None}}).to_list(None)
    result = []
    for s in subs:
        g = await db.groups.find_one({"_id": ObjectId(s["group_id"])}) if ObjectId.is_valid(s.get("group_id") or "") else None
        if not g:
            continue
        svc = await db.services.find_one({"_id": ObjectId(g["service_id"])}) if ObjectId.is_valid(g.get("service_id") or "") else None
        members_subs = await db.subscriptions.find({"group_id": str(g["_id"]), "status": "active"}).to_list(None)
        members = []
        for m in members_subs:
            mu = await db.users.find_one({"_id": ObjectId(m["user_id"])}) if ObjectId.is_valid(m["user_id"]) else None
            members.append({"name": (mu or {}).get("name"), "role": m.get("role"), "is_me": m["user_id"] == user["id"]})
        cred = await db.group_credentials.find_one({"group_id": str(g["_id"])})
        if cred:
            cred["id"] = oid(cred.pop("_id"))
        result.append({
            "group": {"id": str(g["_id"]), "name": g["name"], "notes": g.get("notes"), "status": g.get("status", "active"),
                      "host_slots": g["host_slots"], "regular_slots": g["regular_slots"], "expires_at": g.get("expires_at")},
            "service": {"id": str(svc["_id"]), "name": svc["name"], "slug": svc["slug"], "color": svc.get("color"), "logo_url": svc.get("logo_url")} if svc else None,
            "role": s.get("role"),
            "start_date": s.get("start_date"),
            "members": members,
            "credential": cred,
        })
    return result


# ---------------- Suggest groups for admin ---------------- #
@router.get("/admin/groups/suggest")
async def suggest_groups(service_id: str, role: str = "regular", admin: dict = Depends(require_admin)):
    """Return groups for a service that still have open slots for the given role."""
    groups = await db.groups.find({"service_id": service_id, "active": True, "status": {"$in": ["active", None]}}).to_list(None)
    out = []
    for g in groups:
        gid = str(g["_id"])
        subs = await db.subscriptions.find({"group_id": gid, "status": "active"}).to_list(None)
        filled_host = sum(1 for x in subs if x.get("role") == "host")
        filled_reg = sum(1 for x in subs if x.get("role") == "regular")
        capacity = g["host_slots"] if role == "host" else g["regular_slots"]
        filled = filled_host if role == "host" else filled_reg
        if filled < capacity:
            out.append({
                "id": gid, "name": g["name"],
                "host_slots": g["host_slots"], "regular_slots": g["regular_slots"],
                "filled_host": filled_host, "filled_regular": filled_reg,
                "available_for_role": capacity - filled,
            })
    return out


@router.get("/admin/groups/unassigned-users")
async def unassigned_users_for_service(service_id: str, admin: dict = Depends(require_admin)):
    """Return users who have NO active subscription for this service (or have one but no group_id).
    Useful for group assignment UI so admin sees only relevant candidates."""
    # Users with active sub for this service already having a group
    assigned = await db.subscriptions.find({
        "service_id": service_id,
        "status": "active",
        "group_id": {"$ne": None, "$exists": True},
    }).to_list(None)
    assigned_user_ids = {s["user_id"] for s in assigned if s.get("user_id")}
    # All non-admin users
    users = await db.users.find({"role": {"$ne": "admin"}}).to_list(None)
    out = []
    for u in users:
        uid = str(u["_id"])
        if uid in assigned_user_ids:
            continue
        # Check if user has ANY active sub for this service without a group
        pending_sub = await db.subscriptions.find_one({
            "user_id": uid,
            "service_id": service_id,
            "status": "active",
        })
        out.append({
            "id": uid,
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "has_pending_sub": bool(pending_sub),
            "pending_sub_id": str(pending_sub["_id"]) if pending_sub else None,
            "pending_role": pending_sub.get("role") if pending_sub else None,
        })
    return out


# ---------------- Public: Service availability ---------------- #
@router.get("/public/availability")
async def services_availability():
    services = await db.services.find({"active": True}).to_list(None)
    out = []
    for s in services:
        sid = str(s["_id"])
        groups = await db.groups.find({"service_id": sid, "active": True}).to_list(None)
        total_host = sum(g["host_slots"] for g in groups)
        total_reg = sum(g["regular_slots"] for g in groups)
        subs = await db.subscriptions.find({"service_id": sid, "status": "active", "group_id": {"$ne": None, "$exists": True}}).to_list(None)
        filled_host = sum(1 for x in subs if x.get("role") == "host")
        filled_reg = sum(1 for x in subs if x.get("role") == "regular")
        total_slots = total_host + total_reg
        filled_slots = min(filled_host + filled_reg, total_slots)
        out.append({
            "service_id": sid, "slug": s["slug"], "name": s["name"],
            "total_slots": total_slots, "filled_slots": filled_slots,
            "available_slots": max(0, total_slots - filled_slots),
            "groups": len(groups), "has_availability": max(0, total_slots - filled_slots) > 0,
        })
    return out


# ---------------- Waitlist ---------------- #
@router.post("/waitlist")
async def waitlist_join(input: WaitlistInput):
    doc = input.model_dump()
    doc["created_at"] = now_utc()
    doc["status"] = "new"
    await db.waitlist.insert_one(doc)
    return {"ok": True}


@router.get("/admin/waitlist")
async def admin_list_waitlist(admin: dict = Depends(require_admin)):
    entries = await db.waitlist.find({}).sort("created_at", -1).to_list(None)
    for e in entries:
        e["id"] = oid(e.pop("_id"))
        svc = await db.services.find_one({"_id": ObjectId(e["service_id"])}) if ObjectId.is_valid(e.get("service_id") or "") else None
        e["service_name"] = (svc or {}).get("name")
    return entries


@router.patch("/admin/waitlist/{entry_id}")
async def admin_update_waitlist(entry_id: str, body: dict, admin: dict = Depends(require_admin)):
    allowed = {k: v for k, v in body.items() if k in {"status", "notes"}}
    if allowed:
        await db.waitlist.update_one({"_id": ObjectId(entry_id)}, {"$set": allowed})
    e = await db.waitlist.find_one({"_id": ObjectId(entry_id)})
    if e:
        e["id"] = oid(e.pop("_id"))
    return e


@router.delete("/admin/waitlist/{entry_id}")
async def admin_delete_waitlist(entry_id: str, admin: dict = Depends(require_admin)):
    await db.waitlist.delete_one({"_id": ObjectId(entry_id)})
    return {"ok": True}
