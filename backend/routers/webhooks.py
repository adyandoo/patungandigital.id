"""Webhooks (Midtrans + Xendit) router — split from server.py."""
import os
import logging
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException

from server import (
    db, now_utc, log_admin_action,
    midtrans_verify_signature, midtrans_map_status,
    apply_referral_rewards_if_first_paid, MIDTRANS_SERVER_KEY,
)

logger = logging.getLogger("patungan")
router = APIRouter()


@router.post("/webhooks/midtrans")
async def midtrans_webhook(request: Request):
    """Midtrans notification handler. Signature verified via SHA512."""
    payload = await request.json()
    if MIDTRANS_SERVER_KEY and not midtrans_verify_signature(payload):
        raise HTTPException(status_code=401, detail="invalid signature")
    order_id = payload.get("order_id", "")
    if not order_id.startswith("pd-"):
        return {"ok": True, "note": "ignored (unknown order_id)"}
    payment_id = order_id[3:]
    try:
        obj_id = ObjectId(payment_id)
    except Exception:
        return {"ok": True, "note": "invalid payment id"}
    new_status = midtrans_map_status(payload)
    updates = {
        "status": new_status,
        "midtrans_transaction_id": payload.get("transaction_id"),
        "midtrans_notification": payload,
    }
    if new_status == "paid":
        updates["midtrans_paid_at"] = now_utc()
    await db.payments.update_one({"_id": obj_id}, {"$set": updates})
    if new_status == "paid":
        await apply_referral_rewards_if_first_paid(payment_id)
    await log_admin_action(None, "midtrans_webhook", f"payment:{payment_id}",
                           {"status": new_status, "raw_status": payload.get("transaction_status")})
    return {"ok": True, "status": new_status}


@router.post("/webhooks/xendit")
async def xendit_webhook(request: Request):
    """Legacy Xendit callback (kept for backward compat)."""
    expected_token = os.environ.get("XENDIT_WEBHOOK_TOKEN", "")
    received = request.headers.get("X-CALLBACK-TOKEN", "")
    if expected_token and received != expected_token:
        raise HTTPException(status_code=401, detail="Invalid callback token")
    body = await request.json()
    external_id = body.get("external_id", "")
    status_val = (body.get("status") or "").upper()
    if not external_id.startswith("pay-"):
        return {"ok": True, "note": "ignored (unknown external_id)"}
    payment_id = external_id[4:]
    try:
        obj_id = ObjectId(payment_id)
    except Exception:
        return {"ok": True, "note": "invalid payment id"}
    new_status = None
    if status_val in ("PAID", "SETTLED"):
        new_status = "paid"
    elif status_val in ("EXPIRED", "FAILED"):
        new_status = "overdue"
    if new_status:
        await db.payments.update_one({"_id": obj_id}, {"$set": {"status": new_status, "xendit_paid_at": now_utc()}})
        await log_admin_action(None, "xendit_webhook", f"payment:{payment_id}", {"status": new_status, "raw_status": status_val})
    return {"ok": True, "status": new_status}
