"""Voucher CRUD + user redemption endpoints.
Vouchers can be:
- global (applies_to_user_id=None) — any user can claim once
- targeted (applies_to_user_id=<uid>) — only that user can claim
Sources: admin_manual, leaderboard, referral, etc.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from server import (
    db, now_utc, oid, get_current_user, require_admin,
    log_admin_action, VoucherCreate, VoucherUpdate, VoucherRedeemInput,
)

router = APIRouter()


def _gen_voucher_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    # avoid confusing chars 0/O/1/I
    alphabet = "".join(c for c in alphabet if c not in "O0I1")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _voucher_out(v: dict, redemption_count: Optional[int] = None) -> dict:
    out = {
        "id": str(v["_id"]),
        "code": v.get("code"),
        "description": v.get("description", ""),
        "discount_amount": int(v.get("discount_amount", 0) or 0),
        "discount_percent": float(v.get("discount_percent", 0) or 0),
        "max_uses": int(v.get("max_uses", 1) or 1),
        "used_count": int(v.get("used_count", 0) or 0),
        "valid_until": v.get("valid_until"),
        "status": v.get("status", "active"),
        "applies_to_user_id": v.get("applies_to_user_id"),
        "source": v.get("source", "admin_manual"),
        "created_at": v.get("created_at"),
        "created_by": v.get("created_by"),
    }
    if isinstance(out["valid_until"], datetime):
        out["valid_until"] = out["valid_until"].isoformat()
    if redemption_count is not None:
        out["redemption_count"] = redemption_count
    return out


async def _check_voucher_valid_for_user(v: dict, user_id: str) -> tuple[bool, Optional[str]]:
    """Return (valid, error_message). If valid, error_message is None."""
    if not v:
        return False, "Kode voucher tidak ditemukan."
    if v.get("status") != "active":
        return False, "Voucher tidak aktif."
    valid_until = v.get("valid_until")
    if isinstance(valid_until, datetime):
        vu = valid_until.replace(tzinfo=timezone.utc) if valid_until.tzinfo is None else valid_until
        if vu < now_utc():
            return False, "Voucher sudah expired."
    if int(v.get("used_count", 0) or 0) >= int(v.get("max_uses", 1) or 1):
        return False, "Voucher sudah habis dipakai."
    target = v.get("applies_to_user_id")
    if target and target != user_id:
        return False, "Voucher ini bukan untuk akun kamu."
    # Check per-user redemption (prevent same user redeeming twice)
    already = await db.voucher_redemptions.find_one({"voucher_id": str(v["_id"]), "user_id": user_id})
    if already:
        return False, "Kamu sudah pakai voucher ini sebelumnya."
    return True, None


# ---------------- Admin: CRUD ---------------- #
@router.get("/admin/vouchers")
async def admin_list_vouchers(admin: dict = Depends(require_admin)):
    vouchers = await db.vouchers.find({}).sort("created_at", -1).to_list(None)
    result = []
    for v in vouchers:
        # attach target user info if any
        row = _voucher_out(v)
        tgt = v.get("applies_to_user_id")
        if tgt and ObjectId.is_valid(tgt):
            u = await db.users.find_one({"_id": ObjectId(tgt)}, {"name": 1, "email": 1})
            if u:
                row["target_user"] = {"id": tgt, "name": u.get("name"), "email": u.get("email")}
        result.append(row)
    return result


@router.post("/admin/vouchers")
async def admin_create_voucher(input: VoucherCreate, admin: dict = Depends(require_admin)):
    if input.discount_amount <= 0 and input.discount_percent <= 0:
        raise HTTPException(400, "Voucher harus punya discount_amount atau discount_percent > 0.")
    code = (input.code or _gen_voucher_code()).upper().strip()
    if not code or " " in code or len(code) < 4:
        raise HTTPException(400, "Kode voucher tidak valid (min 4 karakter, tanpa spasi).")
    if await db.vouchers.find_one({"code": code}):
        raise HTTPException(400, f"Kode voucher '{code}' sudah dipakai.")
    if input.applies_to_user_id and not ObjectId.is_valid(input.applies_to_user_id):
        raise HTTPException(400, "applies_to_user_id tidak valid.")
    if input.applies_to_user_id:
        u = await db.users.find_one({"_id": ObjectId(input.applies_to_user_id)})
        if not u:
            raise HTTPException(404, "Target user tidak ditemukan.")
    now = now_utc()
    doc = {
        "code": code,
        "description": input.description,
        "discount_amount": int(input.discount_amount),
        "discount_percent": float(input.discount_percent),
        "max_uses": int(input.max_uses),
        "used_count": 0,
        "valid_until": now + timedelta(days=int(input.valid_days)),
        "applies_to_user_id": input.applies_to_user_id,
        "source": input.source,
        "status": "active",
        "created_at": now,
        "created_by": admin["id"],
    }
    r = await db.vouchers.insert_one(doc)
    doc["_id"] = r.inserted_id
    await log_admin_action(admin, "create_voucher", f"voucher:{code}", {"discount_amount": doc["discount_amount"], "discount_percent": doc["discount_percent"], "source": doc["source"]})
    return _voucher_out(doc)


@router.patch("/admin/vouchers/{voucher_id}")
async def admin_update_voucher(voucher_id: str, input: VoucherUpdate, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(voucher_id):
        raise HTTPException(400, "Invalid voucher id")
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if "valid_until" in updates and isinstance(updates["valid_until"], datetime):
        # keep as datetime for TTL/comparison
        pass
    if updates:
        await db.vouchers.update_one({"_id": ObjectId(voucher_id)}, {"$set": updates})
    v = await db.vouchers.find_one({"_id": ObjectId(voucher_id)})
    if not v:
        raise HTTPException(404, "Voucher tidak ditemukan.")
    await log_admin_action(admin, "update_voucher", f"voucher:{v.get('code')}", updates)
    return _voucher_out(v)


@router.delete("/admin/vouchers/{voucher_id}")
async def admin_delete_voucher(voucher_id: str, admin: dict = Depends(require_admin)):
    if not ObjectId.is_valid(voucher_id):
        raise HTTPException(400, "Invalid voucher id")
    v = await db.vouchers.find_one({"_id": ObjectId(voucher_id)})
    await db.vouchers.delete_one({"_id": ObjectId(voucher_id)})
    await log_admin_action(admin, "delete_voucher", f"voucher:{(v or {}).get('code')}")
    return {"ok": True}


# ---------------- User: list + redeem ---------------- #
@router.get("/me/vouchers")
async def my_vouchers(user: dict = Depends(get_current_user)):
    """Return vouchers targeted to this user + vouchers they've redeemed for their history."""
    now = now_utc()
    # targeted: applies_to_user_id == me AND active AND not expired AND not used up
    targeted = await db.vouchers.find({
        "applies_to_user_id": user["id"],
        "status": "active",
    }).sort("created_at", -1).to_list(None)
    result = []
    for v in targeted:
        vu = v.get("valid_until")
        if isinstance(vu, datetime):
            if (vu.replace(tzinfo=timezone.utc) if vu.tzinfo is None else vu) < now:
                # expired
                row = _voucher_out(v)
                row["is_expired"] = True
                row["is_redeemed"] = False
                result.append(row)
                continue
        already = await db.voucher_redemptions.find_one({"voucher_id": str(v["_id"]), "user_id": user["id"]})
        row = _voucher_out(v)
        row["is_expired"] = False
        row["is_redeemed"] = bool(already)
        if already:
            row["redeemed_at"] = already.get("redeemed_at").isoformat() if isinstance(already.get("redeemed_at"), datetime) else already.get("redeemed_at")
            row["payment_id"] = already.get("payment_id")
        result.append(row)
    return result


@router.post("/me/payments/{payment_id}/apply-voucher")
async def apply_voucher_to_payment(payment_id: str, input: VoucherRedeemInput, user: dict = Depends(get_current_user)):
    """Apply a voucher code to a pending payment.
    - Reduces payment.amount by voucher discount
    - Records redemption
    - Increments voucher.used_count
    - Prevents applying more than one voucher per payment
    """
    if not ObjectId.is_valid(payment_id):
        raise HTTPException(400, "Invalid payment id")
    pay = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not pay:
        raise HTTPException(404, "Tagihan tidak ditemukan.")
    # Verify ownership
    sub = await db.subscriptions.find_one({"_id": ObjectId(pay["subscription_id"])}) if ObjectId.is_valid(pay.get("subscription_id") or "") else None
    if not sub or sub.get("user_id") != user["id"]:
        raise HTTPException(403, "Tagihan ini bukan milikmu.")
    if pay.get("status") != "pending":
        raise HTTPException(400, "Voucher hanya bisa dipakai untuk tagihan yang masih pending.")
    if pay.get("voucher_applied_id"):
        raise HTTPException(400, "Tagihan ini sudah pakai voucher lain.")
    code = input.code.strip().upper()
    v = await db.vouchers.find_one({"code": code})
    ok, err = await _check_voucher_valid_for_user(v, user["id"])
    if not ok:
        raise HTTPException(400, err)
    # Calculate discount
    base_amount = int(pay.get("base_amount", pay.get("amount", 0)) or 0)
    discount = int(v.get("discount_amount", 0) or 0)
    if float(v.get("discount_percent", 0) or 0) > 0:
        discount = max(discount, int(base_amount * float(v["discount_percent"]) / 100))
    discount = min(discount, base_amount)  # cannot exceed base amount
    new_amount = max(0, base_amount - discount)
    now = now_utc()
    # Apply
    await db.payments.update_one(
        {"_id": pay["_id"]},
        {"$set": {
            "amount": new_amount,
            "voucher_applied_id": str(v["_id"]),
            "voucher_code": code,
            "voucher_discount_amount": discount,
        }},
    )
    await db.vouchers.update_one({"_id": v["_id"]}, {"$inc": {"used_count": 1}})
    await db.voucher_redemptions.insert_one({
        "voucher_id": str(v["_id"]),
        "voucher_code": code,
        "user_id": user["id"],
        "payment_id": payment_id,
        "discount_applied": discount,
        "redeemed_at": now,
    })
    return {
        "ok": True,
        "voucher_code": code,
        "discount_applied": discount,
        "new_amount": new_amount,
        "original_amount": base_amount,
    }


@router.post("/me/payments/{payment_id}/remove-voucher")
async def remove_voucher_from_payment(payment_id: str, user: dict = Depends(get_current_user)):
    """Undo an applied voucher (before payment is confirmed)."""
    if not ObjectId.is_valid(payment_id):
        raise HTTPException(400, "Invalid payment id")
    pay = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not pay:
        raise HTTPException(404, "Tagihan tidak ditemukan.")
    sub = await db.subscriptions.find_one({"_id": ObjectId(pay["subscription_id"])}) if ObjectId.is_valid(pay.get("subscription_id") or "") else None
    if not sub or sub.get("user_id") != user["id"]:
        raise HTTPException(403, "Tagihan ini bukan milikmu.")
    if pay.get("status") != "pending":
        raise HTTPException(400, "Voucher hanya bisa dicopot dari tagihan pending.")
    voucher_id = pay.get("voucher_applied_id")
    if not voucher_id:
        raise HTTPException(400, "Tagihan ini belum pakai voucher.")
    base_amount = int(pay.get("base_amount", pay.get("amount", 0)) or 0)
    await db.payments.update_one(
        {"_id": pay["_id"]},
        {"$set": {"amount": base_amount},
         "$unset": {"voucher_applied_id": "", "voucher_code": "", "voucher_discount_amount": ""}},
    )
    # Decrement voucher used_count and remove redemption
    if ObjectId.is_valid(voucher_id):
        await db.vouchers.update_one({"_id": ObjectId(voucher_id)}, {"$inc": {"used_count": -1}})
    await db.voucher_redemptions.delete_one({"voucher_id": voucher_id, "user_id": user["id"], "payment_id": payment_id})
    return {"ok": True, "restored_amount": base_amount}
