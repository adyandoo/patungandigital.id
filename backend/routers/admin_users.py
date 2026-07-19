"""Admin users bulk-import/template/reset-password endpoints — split from server.py.
Note: regular admin user CRUD (list/create/update/delete/bulk-delete) still lives in server.py.
"""
import base64
import csv as _csv
import io as _io
import logging
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from server import (
    db, now_utc, log_admin_action, require_admin,
    hash_password, _csv_stream, _send_email,
    BulkUserImportInput, AdminResetPasswordInput,
)
import os

logger = logging.getLogger("patungan")
router = APIRouter()


@router.get("/admin/users/template.csv")
async def users_import_template(admin: dict = Depends(require_admin)):
    header = ["name", "email", "username", "whatsapp", "gender", "password"]
    sample = [
        ["Budi Santoso", "budi@example.com", "budi", "628123456789", "male", ""],
        ["Ani Wijaya", "ani@example.com", "", "", "female", "mypassword"],
    ]
    resp = _csv_stream(header, sample)
    resp.headers["Content-Disposition"] = 'attachment; filename="users_template.csv"'
    return resp


@router.post("/admin/users/import")
async def import_users_csv(input: BulkUserImportInput, admin: dict = Depends(require_admin)):
    """Bulk import users from CSV. Skips rows with existing email or invalid data."""
    raw = input.file_base64
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(raw).decode("utf-8-sig")
    except Exception:
        raise HTTPException(400, "File tidak bisa dibaca (bukan CSV UTF-8)")
    reader = _csv.DictReader(_io.StringIO(content))
    if not reader.fieldnames or "email" not in [f.lower().strip() for f in reader.fieldnames]:
        raise HTTPException(400, "Kolom 'email' wajib ada di header CSV.")
    def norm(k):
        return (k or "").lower().strip()
    gcfg = await db.settings.find_one({"key": "general_config"}) or {}
    default_pw = gcfg.get("default_new_user_password", "patungan123")
    created, skipped, errors = [], [], []
    for i, raw_row in enumerate(reader, start=2):
        row = {}
        for k, v in raw_row.items():
            if isinstance(v, list):
                v = v[0] if v else ""
            row[norm(k)] = (v or "").strip() if isinstance(v, str) else ""
        email = row.get("email", "").lower()
        name = row.get("name", "") or email.split("@")[0]
        if not email or "@" not in email:
            errors.append({"row": i, "reason": "email invalid", "email": email})
            continue
        if await db.users.find_one({"email": email}):
            skipped.append({"row": i, "reason": "email exists", "email": email})
            continue
        pw = row.get("password") or default_pw
        try:
            doc = {
                "email": email,
                "password_hash": hash_password(pw),
                "name": name,
                "username": row.get("username") or email.split("@")[0],
                "whatsapp": row.get("whatsapp") or "",
                "gender": row.get("gender") or "",
                "role": "user",
                "extra": {},
                "created_at": now_utc().isoformat(),
                "imported": True,
            }
            r = await db.users.insert_one(doc)
            created.append({"row": i, "email": email, "id": str(r.inserted_id)})
        except Exception as e:
            errors.append({"row": i, "reason": "db_error", "email": email})
            logger.warning(f"import user {email} failed: {e}")
    await log_admin_action(admin, "import_users_csv", "users", {
        "created": len(created), "skipped": len(skipped), "errors": len(errors), "default_pw_used": True,
    })
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "summary": {"created": len(created), "skipped": len(skipped), "errors": len(errors)},
        "default_password_used": default_pw,
    }


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(user_id: str, input: AdminResetPasswordInput, admin: dict = Depends(require_admin)):
    """Admin resets a user's password to the global default and (optionally) emails them."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "Invalid user id")
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    if not u:
        raise HTTPException(404, "User tidak ditemukan")
    gcfg = await db.settings.find_one({"key": "general_config"}) or {}
    default_pw = gcfg.get("default_new_user_password", "patungan123")
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": hash_password(default_pw), "password_reset_by_admin_at": now_utc().isoformat()}},
    )
    email_result = {"sent": False, "mocked": True}
    if input.notify_email and u.get("email"):
        html = f"""
        <h2>Password kamu telah di-reset</h2>
        <p>Halo {u.get('name','')},</p>
        <p>Admin telah me-reset password akunmu di <b>patungandigital.id</b>.</p>
        <p>Password baru: <code style="background:#FFD60A;padding:6px 10px;font-weight:bold;">{default_pw}</code></p>
        <p>Silakan login dan segera ganti password lewat menu <b>Password</b> di dashboard.</p>
        <p><a href="{os.environ.get('FRONTEND_URL','').rstrip('/')}/login">Login sekarang</a></p>
        """
        email_result = await _send_email(u["email"], "Password kamu telah di-reset — patungandigital.id", html)
    await log_admin_action(admin, "admin_reset_password", f"user:{user_id}", {"email": u.get("email"), "notified": email_result.get("sent")})
    return {"ok": True, "default_password": default_pw, "email": email_result}
