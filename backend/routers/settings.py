"""Admin settings endpoints — split from server.py.
Covers: payment-config, invoice-config, general-config, and their public counterparts.
"""
from fastapi import APIRouter, Depends

from server import (
    db, log_admin_action, require_admin,
    PaymentConfigInput, InvoiceConfigInput, GeneralConfigInput,
)

router = APIRouter()


# ---------------- Payment config ---------------- #
@router.get("/payment-config")
async def get_payment_config_public():
    """Public endpoint used by user dashboard to render QRIS + fee info + expiry warning window."""
    cfg = await db.settings.find_one({"key": "payment_config"}) or {}
    icfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    return {
        "qris_image_base64": cfg.get("qris_image_base64"),
        "qris_notes": cfg.get("qris_notes", ""),
        "manual_bank_info": cfg.get("manual_bank_info", ""),
        "midtrans_fee_percent": float(cfg.get("midtrans_fee_percent", 5.0) or 5.0),
        "expiry_warning_days": int(icfg.get("expiry_warning_days", 7) or 7),
    }


@router.get("/admin/payment-config")
async def admin_get_payment_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "payment_config"}) or {}
    return {
        "qris_image_base64": cfg.get("qris_image_base64"),
        "qris_notes": cfg.get("qris_notes", ""),
        "manual_bank_info": cfg.get("manual_bank_info", ""),
        "midtrans_fee_percent": float(cfg.get("midtrans_fee_percent", 5.0) or 5.0),
    }


@router.put("/admin/payment-config")
async def admin_set_payment_config(input: PaymentConfigInput, admin: dict = Depends(require_admin)):
    payload = {k: v for k, v in input.model_dump().items() if v is not None}
    payload["key"] = "payment_config"
    await db.settings.update_one({"key": "payment_config"}, {"$set": payload}, upsert=True)
    await log_admin_action(admin, "update_payment_config", "settings", {
        "midtrans_fee_percent": payload.get("midtrans_fee_percent"),
        "qris_updated": bool(input.qris_image_base64),
    })
    return {"ok": True}


# ---------------- Invoice config ---------------- #
@router.get("/admin/invoice-config")
async def get_invoice_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    return {
        "day_of_month": int(cfg.get("day_of_month", 1) or 1),
        "due_days": int(cfg.get("due_days", 7) or 7),
        "enabled": bool(cfg.get("enabled", True)),
        "expiry_warning_days": int(cfg.get("expiry_warning_days", 7) or 7),
        "last_run_period_label": cfg.get("last_run_period_label"),
        "last_run_at": cfg.get("last_run_at"),
    }


@router.put("/admin/invoice-config")
async def set_invoice_config(input: InvoiceConfigInput, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"key": "invoice_config"},
        {"$set": {**input.model_dump(), "key": "invoice_config"}},
        upsert=True,
    )
    await log_admin_action(admin, "update_invoice_config", "settings", input.model_dump())
    return {"ok": True}


# ---------------- General config ---------------- #
@router.get("/admin/general-config")
async def get_general_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "general_config"}) or {}
    return {"default_new_user_password": cfg.get("default_new_user_password", "patungan123")}


@router.put("/admin/general-config")
async def set_general_config(input: GeneralConfigInput, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"key": "general_config"},
        {"$set": {**input.model_dump(), "key": "general_config"}},
        upsert=True,
    )
    await log_admin_action(admin, "update_general_config", "settings", {"password_changed": True})
    return {"ok": True}
