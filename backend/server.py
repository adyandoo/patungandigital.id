"""patungandigital.id — subscription sharing platform backend."""
import os
import io
import csv
import hashlib
import asyncio
import logging
import base64
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

from dotenv import load_dotenv
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field
import bcrypt
import jwt
import httpx


# ---------------- Midtrans config ---------------- #
MIDTRANS_IS_PROD = os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"
MIDTRANS_APP_BASE = "https://app.midtrans.com" if MIDTRANS_IS_PROD else "https://app.sandbox.midtrans.com"
MIDTRANS_API_BASE = "https://api.midtrans.com" if MIDTRANS_IS_PROD else "https://api.sandbox.midtrans.com"
MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "")
REFERRAL_REWARD = int(os.environ.get("REFERRAL_REWARD_IDR", "10000") or "10000")

# ---------------- Mongo setup ---------------- #
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("patungan")


# ---------------- Utils ---------------- #
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: str, kind: str = "access", minutes: int = 60 * 24 * 7) -> str:
    payload = {
        "sub": user_id,
        "type": kind,
        "exp": now_utc() + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def oid(v) -> str:
    return str(v) if v else v


def user_out(u: dict) -> dict:
    if not u:
        return u
    u["id"] = oid(u.pop("_id", u.get("id")))
    u.pop("password_hash", None)
    return u


# ---------------- Auth ---------------- #
async def get_current_user(request: Request) -> dict:
    # 1. Try JWT access_token cookie/header
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
            if user:
                return user_out(user)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
            pass
    # 2. Try Emergent session_token cookie (Google auth path)
    session_token = request.cookies.get("session_token")
    if session_token:
        sess = await db.user_sessions.find_one({"session_token": session_token})
        if sess:
            expires_at = sess.get("expires_at")
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and expires_at > now_utc():
                user = await db.users.find_one({"_id": ObjectId(sess["user_id"])})
                if user:
                    return user_out(user)
    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------------- Referral helpers ---------------- #
TIER_THRESHOLDS = [
    {"tier": 1, "referrals": 5, "free_months": 1, "label": "Tier 1"},
    {"tier": 2, "referrals": 10, "free_months": 2, "label": "Tier 2"},   # cumulative 3 free months
    {"tier": 3, "referrals": 25, "free_months": 5, "label": "Tier 3"},   # cumulative 8 free months
]


async def maybe_grant_tier_rewards(user_id: str):
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return
    successful_refs = await db.users.count_documents({"referred_by": user_id, "first_paid_at": {"$ne": None}})
    granted: List[int] = user.get("tiers_granted", []) or []
    for t in TIER_THRESHOLDS:
        if successful_refs >= t["referrals"] and t["tier"] not in granted:
            await db.users.update_one({"_id": user["_id"]}, {
                "$inc": {"free_months_credit": t["free_months"]},
                "$addToSet": {"tiers_granted": t["tier"]},
            })
            await db.referral_rewards.insert_one({
                "referrer_id": user_id,
                "referred_id": None,
                "payment_id": None,
                "type": f"tier_{t['tier']}",
                "amount": 0,
                "free_months": t["free_months"],
                "created_at": now_utc(),
            })
            await log_admin_action(None, "referral_tier_granted", f"user:{user_id}",
                                   {"tier": t["tier"], "free_months": t["free_months"], "referrals": successful_refs})


def gen_referral_code() -> str:
    # Guarantee >= 8 chars after stripping URL-safe symbols
    raw = secrets.token_urlsafe(16).replace("-", "").replace("_", "").upper()
    return raw[:8]


async def ensure_referral_code(user_id: str) -> str:
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    if u.get("referral_code"):
        return u["referral_code"]
    # generate unique
    for _ in range(10):
        code = gen_referral_code()
        if not await db.users.find_one({"referral_code": code}):
            await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"referral_code": code}})
            return code
    raise HTTPException(500, "Failed to generate referral code")


async def apply_referral_rewards_if_first_paid(payment_id: str):
    """If payment just transitioned to paid, always mark user's first_paid_at.
    If the user was referred and this is their first paid, credit both users."""
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not p or p.get("status") != "paid":
        return
    sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
    if not sub:
        return
    payer = await db.users.find_one({"_id": ObjectId(sub["user_id"])})
    if not payer:
        return
    # Always mark first_paid_at for onboarding + analytics regardless of referral status.
    # Race-safe: only set if not already set (atomic filter). modified_count tells us if we won.
    upd = await db.users.update_one(
        {"_id": payer["_id"], "first_paid_at": None},
        {"$set": {"first_paid_at": now_utc(), "first_paid_payment_id": payment_id}},
    )
    is_first_paid = upd.modified_count == 1
    # Referral reward only when this call actually flipped first_paid_at AND user was referred
    if not (is_first_paid and payer.get("referred_by")):
        return
    referrer_id = payer["referred_by"]
    referrer = await db.users.find_one({"_id": ObjectId(referrer_id)}) if ObjectId.is_valid(referrer_id) else None
    if not referrer:
        return
    # Credit both
    await db.users.update_one({"_id": payer["_id"]}, {"$inc": {"referral_credit": REFERRAL_REWARD}})
    await db.users.update_one({"_id": referrer["_id"]}, {"$inc": {"referral_credit": REFERRAL_REWARD}})
    await db.referral_rewards.insert_one({
        "referrer_id": str(referrer["_id"]),
        "referred_id": str(payer["_id"]),
        "payment_id": payment_id,
        "type": "cash",
        "amount": REFERRAL_REWARD,
        "created_at": now_utc(),
    })
    await log_admin_action(None, "referral_reward_credited", f"user:{payer['_id']}",
                           {"referrer": referrer.get("email"), "referred": payer.get("email"), "amount": REFERRAL_REWARD})
    # Check tier rewards for the referrer
    await maybe_grant_tier_rewards(str(referrer["_id"]))


# ---------------- Midtrans helpers ---------------- #
def midtrans_auth_header() -> str:
    token = base64.b64encode(f"{MIDTRANS_SERVER_KEY}:".encode()).decode()
    return f"Basic {token}"


def midtrans_verify_signature(payload: dict) -> bool:
    raw = f"{payload.get('order_id','')}{payload.get('status_code','')}{payload.get('gross_amount','')}{MIDTRANS_SERVER_KEY}"
    expected = hashlib.sha512(raw.encode()).hexdigest()
    return secrets.compare_digest(expected, payload.get("signature_key", ""))


def midtrans_map_status(payload: dict) -> str:
    ts = payload.get("transaction_status")
    fraud = payload.get("fraud_status")
    if ts == "settlement" or (ts == "capture" and fraud == "accept"):
        return "paid"
    if ts in {"cancel", "deny", "expire", "failure"}:
        return "overdue"
    if ts == "pending":
        return "pending"
    return "pending"


async def midtrans_create_snap(order_id: str, amount: int, customer: dict, item_name: str) -> Optional[dict]:
    if not MIDTRANS_SERVER_KEY:
        return None
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(amount)},
        "customer_details": {"first_name": customer.get("name", ""), "email": customer.get("email", "")},
        "item_details": [{"id": order_id, "price": int(amount), "quantity": 1, "name": item_name[:50]}],
    }
    headers = {"Accept": "application/json", "Content-Type": "application/json", "Authorization": midtrans_auth_header()}
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.post(f"{MIDTRANS_APP_BASE}/snap/v1/transactions", json=payload, headers=headers)
        if r.status_code < 300:
            return r.json()
        logger.warning(f"Midtrans Snap failed {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Midtrans Snap exception: {e}")
    return None


# ---------------- Activity log ---------------- #
async def log_admin_action(admin: Optional[dict], action: str, target: str = "", meta: Optional[dict] = None):
    """Persist an admin action to admin_logs. `admin` can be None for system/scheduler."""
    try:
        await db.admin_logs.insert_one({
            "actor_id": admin.get("id") if admin else None,
            "actor_name": (admin.get("name") if admin else "system") or "system",
            "actor_email": admin.get("email") if admin else "system@patungandigital.id",
            "action": action,
            "target": target,
            "meta": meta or {},
            "created_at": now_utc().isoformat(),
        })
    except Exception as e:
        logger.warning(f"log_admin_action failed: {e}")


# ---------------- Models ---------------- #
class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    username: Optional[str] = None
    whatsapp: Optional[str] = None
    gender: Optional[str] = None
    referral_code: Optional[str] = None


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileInput(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    whatsapp: Optional[str] = None
    gender: Optional[str] = None
    extra: Optional[dict] = None


class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class AdminUserInput(BaseModel):
    email: EmailStr
    password: Optional[str] = None
    name: str
    username: Optional[str] = None
    whatsapp: Optional[str] = None
    gender: Optional[str] = None
    role: str = "user"
    extra: Optional[dict] = None


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    username: Optional[str] = None
    whatsapp: Optional[str] = None
    gender: Optional[str] = None
    role: Optional[str] = None
    extra: Optional[dict] = None
    password: Optional[str] = None


class ServiceInput(BaseModel):
    name: str
    slug: str
    description: Optional[str] = ""
    price_regular: float
    price_host: float = 0
    min_duration_months: int = 1
    logo_url: Optional[str] = None
    color: Optional[str] = "#FF3B30"
    active: bool = True


class ServicePlanInput(BaseModel):
    name: str  # e.g., "Netflix Premium", "Spotify Family"
    host_slots: int = 1
    regular_slots: int = 5
    notes: Optional[str] = ""


class SubscriptionInput(BaseModel):
    user_id: str
    service_id: str
    plan_id: Optional[str] = None  # slot group under service
    group_id: Optional[str] = None
    role: str = "regular"  # host or regular
    start_date: datetime
    end_date: Optional[datetime] = None
    price: float
    status: str = "active"


class SubscriptionUpdate(BaseModel):
    user_id: Optional[str] = None
    service_id: Optional[str] = None
    plan_id: Optional[str] = None
    group_id: Optional[str] = None
    role: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    price: Optional[float] = None
    status: Optional[str] = None


class GroupInput(BaseModel):
    service_id: str
    name: str
    host_slots: int = 1
    regular_slots: int = 4
    notes: Optional[str] = ""
    active: bool = True
    status: Optional[str] = "active"  # active | paused | expired
    expires_at: Optional[datetime] = None


class CredentialInput(BaseModel):
    email: str
    password: str
    notes: Optional[str] = ""


class WaitlistInput(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    whatsapp: Optional[str] = None
    service_id: str
    message: Optional[str] = None


class PaymentInput(BaseModel):
    subscription_id: str
    amount: float
    due_date: Optional[datetime] = None
    period_label: Optional[str] = None  # e.g., "Jan 2026"


class UploadReceiptInput(BaseModel):
    payment_id: str
    file_base64: str  # data:image/png;base64,....
    file_name: str


class ChooseMethodInput(BaseModel):
    method: str  # 'qris' or 'midtrans'


class PaymentConfigInput(BaseModel):
    qris_image_base64: Optional[str] = None  # data URL
    qris_notes: Optional[str] = ""
    midtrans_fee_percent: float = Field(default=5.0, ge=0, le=100)
    manual_bank_info: Optional[str] = ""


class InvoiceConfigInput(BaseModel):
    day_of_month: int = Field(default=1, ge=1, le=28)
    due_days: int = Field(default=7, ge=1, le=60)
    enabled: bool = True


class GeneralConfigInput(BaseModel):
    default_new_user_password: str = Field(default="patungan123", min_length=6)


class CreateAdminInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    username: Optional[str] = None


class ReminderConfigInput(BaseModel):
    days_before_due: int = 3
    enable_email: bool = True
    enable_whatsapp: bool = True
    reminder_message: Optional[str] = "Halo {name}, tagihan {service} untuk {period} akan jatuh tempo pada {due_date}. Jumlah: Rp {amount}."


# ---------------- App ---------------- #
_scheduler_stop = asyncio.Event()


async def _reminder_scheduler_loop():
    """Background loop: every hour, scan pending payments due within `days_before_due`
    that have not received a reminder in the last 24h, and send them."""
    logger.info("Reminder scheduler started (interval=1h)")
    # Small initial delay so app fully starts
    try:
        await asyncio.wait_for(_scheduler_stop.wait(), timeout=30)
        return
    except asyncio.TimeoutError:
        pass
    while not _scheduler_stop.is_set():
        try:
            await _run_due_reminders(actor=None)
        except Exception as e:
            logger.warning(f"scheduler tick failed: {e}")
        try:
            await _run_invoice_generator(actor=None)
        except Exception as e:
            logger.warning(f"invoice generator tick failed: {e}")
        try:
            await asyncio.wait_for(_scheduler_stop.wait(), timeout=3600)
        except asyncio.TimeoutError:
            continue


async def _run_invoice_generator(actor: Optional[dict] = None, force: bool = False) -> dict:
    """Generate invoices for active subscriptions on configured day of month.
    Idempotent: skips if a payment for (subscription_id, period_label) already exists."""
    cfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    if not cfg.get("enabled", True) and not force:
        return {"count": 0, "skipped": "disabled"}
    day = int(cfg.get("day_of_month", 1) or 1)
    due_days = int(cfg.get("due_days", 7) or 7)
    now = now_utc()
    if not force and now.day != day:
        return {"count": 0, "skipped": f"not scheduled day (today={now.day}, target={day})"}
    period_label = now.strftime("%b %Y")  # e.g. "Feb 2026"
    active_subs = await db.subscriptions.find({"status": "active"}).to_list(None)
    created = []
    skipped = []
    for sub in active_subs:
        exists = await db.payments.find_one({
            "subscription_id": str(sub["_id"]),
            "period_label": period_label,
        })
        if exists:
            skipped.append(str(sub["_id"]))
            continue
        due = now + timedelta(days=due_days)
        doc = {
            "subscription_id": str(sub["_id"]),
            "amount": int(sub.get("price", 0)),
            "base_amount": int(sub.get("price", 0)),
            "period_label": period_label,
            "due_date": due,
            "status": "pending",
            "created_at": now.isoformat(),
            "receipt": None,
            "payment_method": None,
            "auto_generated": True,
        }
        res = await db.payments.insert_one(doc)
        created.append(str(res.inserted_id))
    await log_admin_action(actor, "invoice_generator_run", "payments", {
        "period": period_label, "created": len(created), "skipped": len(skipped), "forced": force,
    })
    return {"count": len(created), "created": created, "skipped": len(skipped), "period": period_label}


async def _run_due_reminders(actor: Optional[dict] = None) -> dict:
    cfg = await db.settings.find_one({"key": "reminder_config"}) or {}
    days = int(cfg.get("days_before_due", 3) or 3)
    now = now_utc()
    threshold = now + timedelta(days=days)
    yesterday = now - timedelta(hours=24)
    q = {
        "status": {"$in": ["pending", "review"]},
        "due_date": {"$lte": threshold, "$ne": None},
        "$or": [{"last_reminder_at": None}, {"last_reminder_at": {"$lte": yesterday}}, {"last_reminder_at": {"$exists": False}}],
    }
    to_send = await db.payments.find(q).to_list(None)
    sent = []
    for p in to_send:
        try:
            r = await _send_reminder_for_payment(str(p["_id"]), actor=actor)
            sent.append({"payment_id": str(p["_id"]), **{k: r.get(k) for k in ("email_sent", "whatsapp_sent", "mocked")}})
        except Exception as e:
            logger.warning(f"scheduler send failed for {p['_id']}: {e}")
    # H-7 admin group expiry reminders (log-only for now)
    expiring_threshold = now + timedelta(days=7)
    expiring_soon = await db.groups.find({
        "expires_at": {"$ne": None, "$lte": expiring_threshold, "$gte": now},
        "status": "active",
        "expiry_reminder_sent": {"$ne": True},
    }).to_list(None)
    for g in expiring_soon:
        await db.groups.update_one({"_id": g["_id"]}, {"$set": {"expiry_reminder_sent": True}})
        await log_admin_action(None, "group_expiry_reminder", f"group:{g['_id']}", {
            "name": g.get("name"), "expires_at": str(g.get("expires_at")),
        })
        logger.info(f"[ADMIN NOTICE] Group {g.get('name')} akan expired {g.get('expires_at')} — waktunya perpanjang.")
    await log_admin_action(actor, "scheduler_run", "reminders", {"count": len(sent), "days_before_due": days, "expiring_groups": len(expiring_soon)})
    return {"count": len(sent), "sent": sent, "expiring_groups": len(expiring_soon)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username")
    await db.services.create_index("slug", unique=True)
    await db.subscriptions.create_index("user_id")
    await db.payments.create_index("subscription_id")
    await db.payments.create_index("due_date")
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at")
    await db.admin_logs.create_index("created_at")
    # P2: Migrate string dates → BSON dates for scheduler-critical fields
    async for p in db.payments.find({"due_date": {"$type": "string"}}):
        try:
            await db.payments.update_one({"_id": p["_id"]}, {"$set": {"due_date": datetime.fromisoformat(p["due_date"])}})
        except Exception:
            pass
    async for p in db.payments.find({"last_reminder_at": {"$type": "string"}}):
        try:
            await db.payments.update_one({"_id": p["_id"]}, {"$set": {"last_reminder_at": datetime.fromisoformat(p["last_reminder_at"])}})
        except Exception:
            pass
    # Backfill referral codes for users that don't have one
    async for u in db.users.find({"$or": [{"referral_code": None}, {"referral_code": {"$exists": False}}]}):
        try:
            for _ in range(5):
                code = gen_referral_code()
                if not await db.users.find_one({"referral_code": code}):
                    await db.users.update_one({"_id": u["_id"]}, {"$set": {"referral_code": code, "referral_credit": u.get("referral_credit", 0)}})
                    break
        except Exception:
            pass
    await db.users.create_index("referral_code", unique=True, sparse=True)
    await db.referral_rewards.create_index("referrer_id")
    # Seed admin (never force-reset password so admin can change it after login)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@patungandigital.id")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Administrator",
            "username": "admin",
            "role": "admin",
            "created_at": now_utc().isoformat(),
        })
        logger.info(f"Seeded admin user: {admin_email}")
    # One-off cleanup: legacy orphan subscription with user_id='0'
    orphan = await db.subscriptions.delete_many({"user_id": "0"})
    if orphan.deleted_count:
        logger.info(f"Cleaned {orphan.deleted_count} orphan subscription(s) with user_id='0'")
    # Seed default payment_config (5% Midtrans fee, empty QRIS)
    if not await db.settings.find_one({"key": "payment_config"}):
        await db.settings.insert_one({
            "key": "payment_config",
            "qris_image_base64": None,
            "qris_notes": "Scan QRIS lalu upload bukti transfer. Otomatis diverifikasi.",
            "manual_bank_info": "",
            "midtrans_fee_percent": 5.0,
        })
    # Seed default invoice_config (auto-generate on 1st, due in 7 days)
    if not await db.settings.find_one({"key": "invoice_config"}):
        await db.settings.insert_one({
            "key": "invoice_config",
            "day_of_month": 1,
            "due_days": 7,
            "enabled": True,
        })
    # Seed default general_config (bulk-import default password)
    if not await db.settings.find_one({"key": "general_config"}):
        await db.settings.insert_one({
            "key": "general_config",
            "default_new_user_password": "patungan123",
        })
    # Seed default reminder config
    if not await db.settings.find_one({"key": "reminder_config"}):
        await db.settings.insert_one({
            "key": "reminder_config",
            "days_before_due": 3,
            "enable_email": True,
            "enable_whatsapp": True,
            "reminder_message": "Halo {name}, tagihan {service} untuk {period} akan jatuh tempo pada {due_date}. Jumlah: Rp {amount}.",
        })
    # Seed default services
    if await db.services.count_documents({}) == 0:
        seed_services = [
            {"name": "Netflix Premium", "slug": "netflix", "description": "Nikmati Netflix Premium bersama teman. 4K UHD, hingga 4 device.", "price_regular": 45000, "price_host": 0, "min_duration_months": 1, "logo_url": "https://images.pexels.com/photos/5852131/pexels-photo-5852131.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940", "color": "#E50914", "active": True, "created_at": now_utc().isoformat()},
            {"name": "Spotify Family", "slug": "spotify", "description": "Musik tanpa iklan, unduh lagu favorit. Hingga 6 anggota.", "price_regular": 25000, "price_host": 0, "min_duration_months": 1, "logo_url": "https://images.pexels.com/photos/31113917/pexels-photo-31113917.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940", "color": "#1DB954", "active": True, "created_at": now_utc().isoformat()},
            {"name": "YouTube Premium", "slug": "youtube", "description": "Bebas iklan, background play, YouTube Music. 6 anggota keluarga.", "price_regular": 30000, "price_host": 0, "min_duration_months": 1, "logo_url": "https://images.unsplash.com/photo-1705904506626-aba18263a2c7?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NjZ8MHwxfHNlYXJjaHwyfHx5b3V0dWJlJTIwbG9nbyUyMHJlZCUyMGJhY2tncm91bmR8ZW58MHx8fHwxNzg0MzgwOTAwfDA&ixlib=rb-4.1.0&q=85", "color": "#FF0000", "active": True, "created_at": now_utc().isoformat()},
        ]
        await db.services.insert_many(seed_services)
        # add default plans
        for svc in await db.services.find({}).to_list(None):
            if svc["slug"] == "netflix":
                await db.plans.insert_one({"service_id": str(svc["_id"]), "name": "Netflix Premium (4 slot)", "host_slots": 0, "regular_slots": 4, "notes": "", "created_at": now_utc().isoformat()})
            elif svc["slug"] == "spotify":
                await db.plans.insert_one({"service_id": str(svc["_id"]), "name": "Spotify Family (1 host + 5)", "host_slots": 1, "regular_slots": 5, "notes": "", "created_at": now_utc().isoformat()})
            elif svc["slug"] == "youtube":
                await db.plans.insert_one({"service_id": str(svc["_id"]), "name": "YouTube Premium (1 host + 5)", "host_slots": 1, "regular_slots": 5, "notes": "", "created_at": now_utc().isoformat()})
    # Start background reminder scheduler
    scheduler_task = asyncio.create_task(_reminder_scheduler_loop())
    yield
    _scheduler_stop.set()
    scheduler_task.cancel()
    client.close()


app = FastAPI(lifespan=lifespan)
api = APIRouter(prefix="/api")


# ---------------- Auth routes ---------------- #
@api.post("/auth/register")
async def register(input: RegisterInput, response: Response):
    email = input.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    referred_by = None
    if input.referral_code:
        referrer = await db.users.find_one({"referral_code": input.referral_code.strip().upper()})
        if referrer:
            referred_by = str(referrer["_id"])
    doc = {
        "email": email,
        "password_hash": hash_password(input.password),
        "name": input.name,
        "username": input.username or email.split("@")[0],
        "whatsapp": input.whatsapp,
        "gender": input.gender,
        "role": "user",
        "extra": {},
        "referred_by": referred_by,
        "referral_code": None,
        "referral_credit": 0,
        "created_at": now_utc().isoformat(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    # generate referral code
    await ensure_referral_code(str(result.inserted_id))
    doc = await db.users.find_one({"_id": result.inserted_id})
    token = create_token(str(result.inserted_id))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"user": user_out(doc), "token": token}


@api.post("/auth/login")
async def login(input: LoginInput, response: Response):
    email = input.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    # Ensure referral code exists for legacy users
    if not user.get("referral_code"):
        await ensure_referral_code(str(user["_id"]))
        user = await db.users.find_one({"_id": user["_id"]})
    token = create_token(str(user["_id"]))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"user": user_out(user), "token": token}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/change-password")
async def change_password(input: ChangePasswordInput, user: dict = Depends(get_current_user)):
    full = await db.users.find_one({"_id": ObjectId(user["id"])})
    if not verify_password(input.current_password, full["password_hash"]):
        raise HTTPException(status_code=400, detail="Password saat ini salah")
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"password_hash": hash_password(input.new_password)}})
    return {"ok": True}


@api.patch("/auth/profile")
async def update_profile(input: UpdateProfileInput, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": updates})
    updated = await db.users.find_one({"_id": ObjectId(user["id"])})
    return user_out(updated)


# ---------------- Public: services ---------------- #
@api.get("/services")
async def list_services_public():
    svcs = await db.services.find({"active": True}).to_list(None)
    for s in svcs:
        s["id"] = oid(s.pop("_id"))
    return svcs


@api.get("/services/{service_id}")
async def get_service(service_id: str):
    s = await db.services.find_one({"_id": ObjectId(service_id)})
    if not s:
        raise HTTPException(404, "Service not found")
    s["id"] = oid(s.pop("_id"))
    plans = await db.plans.find({"service_id": service_id}).to_list(None)
    for p in plans:
        p["id"] = oid(p.pop("_id"))
    s["plans"] = plans
    return s


# ---------------- Admin: users ---------------- #
@api.get("/admin/users")
async def admin_list_users(user: dict = Depends(require_admin)):
    users = await db.users.find({}).to_list(None)
    return [user_out(u) for u in users]


@api.post("/admin/users")
async def admin_create_user(input: AdminUserInput, admin: dict = Depends(require_admin)):
    email = input.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email sudah terdaftar")
    doc = input.model_dump()
    doc["email"] = email
    doc["password_hash"] = hash_password(input.password or "password123")
    doc.pop("password")
    doc.setdefault("extra", {})
    doc["created_at"] = now_utc().isoformat()
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    await log_admin_action(admin, "create_user", f"user:{result.inserted_id}", {"email": doc["email"], "role": doc.get("role")})
    return user_out(doc)


@api.patch("/admin/users/{user_id}")
async def admin_update_user(user_id: str, input: AdminUserUpdate, admin: dict = Depends(require_admin)):
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if "password" in updates:
        updates["password_hash"] = hash_password(updates.pop("password"))
    if "email" in updates:
        updates["email"] = updates["email"].lower()
    if updates:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": updates})
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    return user_out(u)


@api.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(require_admin)):
    victim = await db.users.find_one({"_id": ObjectId(user_id)})
    await db.users.delete_one({"_id": ObjectId(user_id)})
    await db.subscriptions.delete_many({"user_id": user_id})
    await log_admin_action(admin, "delete_user", f"user:{user_id}", {"email": (victim or {}).get("email")})
    return {"ok": True}


# ---------------- Admin: services ---------------- #
@api.get("/admin/services")
async def admin_list_services(admin: dict = Depends(require_admin)):
    svcs = await db.services.find({}).to_list(None)
    for s in svcs:
        s["id"] = oid(s.pop("_id"))
    return svcs


@api.post("/admin/services")
async def admin_create_service(input: ServiceInput, admin: dict = Depends(require_admin)):
    if await db.services.find_one({"slug": input.slug}):
        raise HTTPException(400, "Slug sudah dipakai")
    doc = input.model_dump()
    doc["created_at"] = now_utc().isoformat()
    result = await db.services.insert_one(doc)
    doc["id"] = oid(result.inserted_id)
    doc.pop("_id", None)
    return doc


@api.patch("/admin/services/{service_id}")
async def admin_update_service(service_id: str, input: ServiceInput, admin: dict = Depends(require_admin)):
    await db.services.update_one({"_id": ObjectId(service_id)}, {"$set": input.model_dump()})
    s = await db.services.find_one({"_id": ObjectId(service_id)})
    s["id"] = oid(s.pop("_id"))
    return s


@api.delete("/admin/services/{service_id}")
async def admin_delete_service(service_id: str, admin: dict = Depends(require_admin)):
    svc = await db.services.find_one({"_id": ObjectId(service_id)})
    await db.services.delete_one({"_id": ObjectId(service_id)})
    await db.plans.delete_many({"service_id": service_id})
    await log_admin_action(admin, "delete_service", f"service:{service_id}", {"name": (svc or {}).get("name")})
    return {"ok": True}


# plans
@api.get("/admin/services/{service_id}/plans")
async def list_plans(service_id: str, admin: dict = Depends(require_admin)):
    plans = await db.plans.find({"service_id": service_id}).to_list(None)
    for p in plans:
        p["id"] = oid(p.pop("_id"))
    return plans


@api.post("/admin/services/{service_id}/plans")
async def create_plan(service_id: str, input: ServicePlanInput, admin: dict = Depends(require_admin)):
    doc = input.model_dump()
    doc["service_id"] = service_id
    doc["created_at"] = now_utc().isoformat()
    result = await db.plans.insert_one(doc)
    doc["id"] = oid(result.inserted_id)
    doc.pop("_id", None)
    return doc


@api.delete("/admin/plans/{plan_id}")
async def delete_plan(plan_id: str, admin: dict = Depends(require_admin)):
    await db.plans.delete_one({"_id": ObjectId(plan_id)})
    return {"ok": True}


# ---------------- Admin: subscriptions ---------------- #
@api.get("/admin/subscriptions")
async def admin_list_subs(admin: dict = Depends(require_admin)):
    subs = await db.subscriptions.find({}).to_list(None)
    for s in subs:
        s["id"] = oid(s.pop("_id"))
        u = await db.users.find_one({"_id": ObjectId(s["user_id"])}) if ObjectId.is_valid(s.get("user_id") or "") else None
        s["user"] = user_out(u) if u else None
        svc = await db.services.find_one({"_id": ObjectId(s["service_id"])}) if ObjectId.is_valid(s.get("service_id") or "") else None
        if svc:
            svc["id"] = oid(svc.pop("_id"))
            s["service"] = svc
    return subs


@api.post("/admin/subscriptions")
async def admin_create_sub(input: SubscriptionInput, admin: dict = Depends(require_admin)):
    doc = input.model_dump()
    doc["start_date"] = doc["start_date"].isoformat() if doc.get("start_date") else None
    doc["end_date"] = doc["end_date"].isoformat() if doc.get("end_date") else None
    doc["created_at"] = now_utc().isoformat()
    result = await db.subscriptions.insert_one(doc)
    doc["id"] = oid(result.inserted_id)
    doc.pop("_id", None)
    return doc


@api.patch("/admin/subscriptions/{sub_id}")
async def admin_update_sub(sub_id: str, input: SubscriptionUpdate, admin: dict = Depends(require_admin)):
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if "start_date" in updates and isinstance(updates["start_date"], datetime):
        updates["start_date"] = updates["start_date"].isoformat()
    if "end_date" in updates and isinstance(updates["end_date"], datetime):
        updates["end_date"] = updates["end_date"].isoformat()
    if updates:
        await db.subscriptions.update_one({"_id": ObjectId(sub_id)}, {"$set": updates})
    s = await db.subscriptions.find_one({"_id": ObjectId(sub_id)})
    s["id"] = oid(s.pop("_id"))
    return s


@api.delete("/admin/subscriptions/{sub_id}")
async def admin_delete_sub(sub_id: str, admin: dict = Depends(require_admin)):
    await db.subscriptions.delete_one({"_id": ObjectId(sub_id)})
    await log_admin_action(admin, "delete_subscription", f"subscription:{sub_id}")
    return {"ok": True}


# ---------------- User: subscriptions ---------------- #
@api.get("/me/subscriptions")
async def my_subscriptions(user: dict = Depends(get_current_user)):
    subs = await db.subscriptions.find({"user_id": user["id"]}).to_list(None)
    for s in subs:
        s["id"] = oid(s.pop("_id"))
        svc = await db.services.find_one({"_id": ObjectId(s["service_id"])})
        if svc:
            svc["id"] = oid(svc.pop("_id"))
            s["service"] = svc
    return subs


# ---------------- Payments ---------------- #
@api.get("/me/payments")
async def my_payments(user: dict = Depends(get_current_user)):
    subs = await db.subscriptions.find({"user_id": user["id"]}).to_list(None)
    sub_ids = [str(s["_id"]) for s in subs]
    pays = await db.payments.find({"subscription_id": {"$in": sub_ids}}).to_list(None)
    for p in pays:
        p["id"] = oid(p.pop("_id"))
        # attach service info
        sub = next((s for s in subs if str(s["_id"]) == p["subscription_id"]), None)
        if sub:
            svc = await db.services.find_one({"_id": ObjectId(sub["service_id"])})
            if svc:
                p["service_name"] = svc["name"]
    # sort by created_at desc
    pays.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return pays


@api.post("/admin/payments")
async def admin_create_payment(input: PaymentInput, admin: dict = Depends(require_admin)):
    doc = input.model_dump()
    doc["due_date"] = input.due_date if input.due_date else None
    doc["status"] = "pending"
    doc["created_at"] = now_utc().isoformat()
    doc["receipt"] = None
    doc["payment_method"] = None  # user picks QRIS or Midtrans
    doc["base_amount"] = int(input.amount)  # remember original before credits/fees
    # Referral credit application: subtract available credit from user
    sub = await db.subscriptions.find_one({"_id": ObjectId(doc["subscription_id"])})
    payer = await db.users.find_one({"_id": ObjectId(sub["user_id"])}) if sub else None
    applied_credit = 0
    if payer and payer.get("free_months_credit", 0) > 0:
        # Free month: amount → 0
        doc["amount"] = 0
        doc["base_amount"] = 0
        doc["free_month_applied"] = True
        await db.users.update_one({"_id": payer["_id"]}, {"$inc": {"free_months_credit": -1}})
    elif payer and payer.get("referral_credit", 0) > 0:
        applied_credit = min(int(payer["referral_credit"]), int(doc["amount"]))
        doc["amount"] = int(doc["amount"]) - applied_credit
        doc["base_amount"] = int(doc["amount"])
        doc["referral_credit_applied"] = applied_credit
        await db.users.update_one({"_id": payer["_id"]}, {"$inc": {"referral_credit": -applied_credit}})
    # Insert (no Midtrans snap yet — user chooses method later)
    result = await db.payments.insert_one(doc)
    doc["id"] = oid(result.inserted_id)
    doc.pop("_id", None)
    if doc.get("due_date") and isinstance(doc["due_date"], datetime):
        doc["due_date"] = doc["due_date"].isoformat()
    return doc


@api.post("/me/payments/{payment_id}/choose-method")
async def choose_payment_method(payment_id: str, input: ChooseMethodInput, user: dict = Depends(get_current_user)):
    """User picks QRIS (manual, 0% fee) or Midtrans (auto, +5% fee)."""
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not p:
        raise HTTPException(404, "Payment not found")
    sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
    if not sub or sub["user_id"] != user["id"]:
        raise HTTPException(403, "Bukan pembayaran Anda")
    if input.method not in {"qris", "midtrans"}:
        raise HTTPException(400, "Metode tidak valid")
    if p.get("status") == "paid":
        raise HTTPException(400, "Pembayaran sudah lunas")
    cfg = await db.settings.find_one({"key": "payment_config"}) or {}
    fee_pct = float(cfg.get("midtrans_fee_percent", 5.0) or 5.0)
    base = int(p.get("base_amount") or p.get("amount", 0))
    updates = {"payment_method": input.method}
    if input.method == "qris":
        updates["amount"] = base
        updates["midtrans_fee"] = 0
        # clear any stale midtrans snap
        updates["midtrans_redirect_url"] = None
        updates["midtrans_token"] = None
    else:  # midtrans
        fee = int(round(base * fee_pct / 100.0))
        final_amount = base + fee
        updates["amount"] = final_amount
        updates["midtrans_fee"] = fee
        updates["midtrans_fee_percent"] = fee_pct
        # Create snap
        payer = await db.users.find_one({"_id": ObjectId(sub["user_id"])})
        svc = await db.services.find_one({"_id": ObjectId(sub["service_id"])})
        order_id = f"pd-{payment_id}-{int(now_utc().timestamp())}"
        snap = await midtrans_create_snap(
            order_id=order_id,
            amount=final_amount,
            customer={"name": (payer or {}).get("name", ""), "email": (payer or {}).get("email", "")},
            item_name=f"{(svc or {}).get('name','Subscription')} — {p.get('period_label','')}",
        )
        if snap:
            updates["midtrans_order_id"] = order_id
            updates["midtrans_token"] = snap.get("token")
            updates["midtrans_redirect_url"] = snap.get("redirect_url")
        else:
            raise HTTPException(502, "Gagal membuat invoice Midtrans. Coba lagi atau pilih QRIS.")
    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": updates})
    p.update(updates)
    p["id"] = oid(p.pop("_id"))
    if isinstance(p.get("due_date"), datetime):
        p["due_date"] = p["due_date"].isoformat()
    return p


@api.get("/admin/payments")
async def admin_list_payments(admin: dict = Depends(require_admin)):
    pays = await db.payments.find({}).to_list(None)
    for p in pays:
        p["id"] = oid(p.pop("_id"))
        sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
        if sub:
            u = await db.users.find_one({"_id": ObjectId(sub["user_id"])})
            p["user"] = user_out(u) if u else None
            svc = await db.services.find_one({"_id": ObjectId(sub["service_id"])})
            if svc:
                p["service_name"] = svc["name"]
    pays.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return pays


@api.patch("/admin/payments/{payment_id}")
async def admin_update_payment(payment_id: str, body: dict, admin: dict = Depends(require_admin)):
    allowed = {k: v for k, v in body.items() if k in {"status", "amount", "due_date", "period_label"}}
    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": allowed})
    if allowed.get("status") == "paid":
        await apply_referral_rewards_if_first_paid(payment_id)
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    p["id"] = oid(p.pop("_id"))
    return p


@api.post("/me/payments/{payment_id}/receipt")
async def upload_receipt(payment_id: str, input: UploadReceiptInput, user: dict = Depends(get_current_user)):
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not p:
        raise HTTPException(404, "Payment not found")
    sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
    if not sub or sub["user_id"] != user["id"]:
        raise HTTPException(403, "Bukan pembayaran Anda")
    receipt = {
        "file_base64": input.file_base64,
        "file_name": input.file_name,
        "uploaded_at": now_utc().isoformat(),
    }
    # Auto-approve on receipt upload (admin can refund/reject later)
    updates = {
        "receipt": receipt,
        "status": "paid",
        "auto_approved_at": now_utc().isoformat(),
    }
    if not p.get("payment_method"):
        updates["payment_method"] = "qris"
    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": updates})
    # Trigger referral rewards (first paid, race-safe inside helper)
    try:
        await apply_referral_rewards_if_first_paid(payment_id)
    except Exception as e:
        logger.warning(f"referral apply on upload failed: {e}")
    return {"ok": True, "receipt": receipt, "status": "paid"}


# ---------------- Admin: Reminder config ---------------- #
@api.get("/admin/reminder-config")
async def get_reminder_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "reminder_config"})
    if cfg:
        cfg.pop("_id", None)
    return cfg or {}


@api.put("/admin/reminder-config")
async def set_reminder_config(input: ReminderConfigInput, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"key": "reminder_config"},
        {"$set": {**input.model_dump(), "key": "reminder_config"}},
        upsert=True,
    )
    return {"ok": True}


@api.post("/admin/send-reminder/{payment_id}")
async def send_reminder(payment_id: str, admin: dict = Depends(require_admin)):
    """Manual reminder trigger for a single payment."""
    result = await _send_reminder_for_payment(payment_id, actor=admin)
    if result.get("error"):
        raise HTTPException(status_code=404 if result["error"] == "not_found" else 500, detail=result["error"])
    return result


async def _send_reminder_for_payment(payment_id: str, actor: Optional[dict] = None) -> dict:
    """Core reminder logic (usable by manual endpoint + scheduler)."""
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not p:
        return {"error": "not_found"}
    sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
    if not sub:
        return {"error": "sub_missing"}
    user = await db.users.find_one({"_id": ObjectId(sub["user_id"])})
    svc = await db.services.find_one({"_id": ObjectId(sub["service_id"])})
    cfg = await db.settings.find_one({"key": "reminder_config"}) or {}
    msg_template = cfg.get("reminder_message") or "Halo {name}, tagihan {service} untuk {period} akan jatuh tempo pada {due_date}. Jumlah: Rp {amount}."
    due_display = p.get("due_date", "")
    if isinstance(due_display, datetime):
        due_display = due_display.strftime("%d %b %Y")
    msg = msg_template.format(
        name=(user or {}).get("name", ""),
        service=(svc or {}).get("name", ""),
        period=p.get("period_label", ""),
        due_date=due_display,
        amount=f"{int(p.get('amount', 0)):,}".replace(",", "."),
    )
    email_sent = False
    wa_sent = False
    mocked = False
    if cfg.get("enable_email", True) and os.environ.get("SENDGRID_API_KEY"):
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            m = Mail(
                from_email=os.environ.get("SENDGRID_FROM_EMAIL"),
                to_emails=user["email"],
                subject=f"Pengingat Pembayaran {svc['name']} - patungandigital.id",
                plain_text_content=msg,
            )
            await asyncio.get_event_loop().run_in_executor(None, lambda: SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(m))
            email_sent = True
        except Exception as e:
            logger.warning(f"SendGrid error: {e}")
    else:
        mocked = True
        logger.info(f"[MOCK EMAIL] to={(user or {}).get('email')} msg={msg}")
    if cfg.get("enable_whatsapp", True) and os.environ.get("TWILIO_ACCOUNT_SID") and (user or {}).get("whatsapp"):
        try:
            from twilio.rest import Client as TwilioClient
            def _send_wa():
                tc = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
                tc.messages.create(from_=os.environ.get("TWILIO_WHATSAPP_FROM"), to=f"whatsapp:{user['whatsapp']}", body=msg)
            await asyncio.get_event_loop().run_in_executor(None, _send_wa)
            wa_sent = True
        except Exception as e:
            logger.warning(f"Twilio error: {e}")
    else:
        mocked = True
        logger.info(f"[MOCK WHATSAPP] to={(user or {}).get('whatsapp')} msg={msg}")

    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": {"last_reminder_at": now_utc()}})
    await log_admin_action(actor, "send_reminder", f"payment:{payment_id}", {"email_sent": email_sent, "whatsapp_sent": wa_sent, "mocked": mocked, "user": (user or {}).get("email")})
    return {"email_sent": email_sent, "whatsapp_sent": wa_sent, "mocked": mocked, "message": msg, "payment_id": payment_id}


# ---------------- Admin: stats ---------------- #
@api.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    return {
        "users": await db.users.count_documents({"role": "user"}),
        "services": await db.services.count_documents({}),
        "active_subscriptions": await db.subscriptions.count_documents({"status": "active"}),
        "pending_payments": await db.payments.count_documents({"status": "pending"}),
    }


# ---------------- Admin: Activity log ---------------- #
@api.get("/admin/logs")
async def admin_list_logs(admin: dict = Depends(require_admin), limit: int = 100, skip: int = 0):
    total = await db.admin_logs.count_documents({})
    logs = await db.admin_logs.find({}).sort("created_at", -1).skip(skip).limit(min(limit, 500)).to_list(None)
    for l in logs:
        l["id"] = oid(l.pop("_id"))
    return {"total": total, "logs": logs}


# ---------------- Admin: Bulk actions ---------------- #
class BulkIdsInput(BaseModel):
    ids: List[str]


@api.post("/admin/users/bulk-delete")
async def bulk_delete_users(input: BulkIdsInput, admin: dict = Depends(require_admin)):
    # never allow deleting admins via bulk
    obj_ids = [ObjectId(i) for i in input.ids]
    targets = await db.users.find({"_id": {"$in": obj_ids}, "role": {"$ne": "admin"}}).to_list(None)
    ids_to_delete = [t["_id"] for t in targets]
    deleted = 0
    if ids_to_delete:
        r = await db.users.delete_many({"_id": {"$in": ids_to_delete}})
        deleted = r.deleted_count
        await db.subscriptions.delete_many({"user_id": {"$in": [str(x) for x in ids_to_delete]}})
    await log_admin_action(admin, "bulk_delete_users", "users", {"count": deleted, "requested": len(input.ids)})
    return {"deleted": deleted, "skipped_admins": len(input.ids) - deleted}


@api.post("/admin/payments/bulk-remind")
async def bulk_remind_payments(input: BulkIdsInput, admin: dict = Depends(require_admin)):
    results = []
    for pid in input.ids:
        r = await _send_reminder_for_payment(pid, actor=admin)
        results.append({"payment_id": pid, **r})
    await log_admin_action(admin, "bulk_send_reminder", "payments", {"count": len(results)})
    return {"count": len(results), "results": results}


# ---------------- Admin: CSV export ---------------- #
def _csv_stream(headers: List[str], rows: List[List[str]]) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv")


@api.get("/admin/users/export.csv")
async def export_users_csv(admin: dict = Depends(require_admin)):
    users = await db.users.find({}).to_list(None)
    rows = [[
        str(u.get("_id")), u.get("name", ""), u.get("username", ""), u.get("email", ""),
        u.get("whatsapp", "") or "", u.get("gender", "") or "", u.get("role", ""), u.get("created_at", "") or "",
    ] for u in users]
    resp = _csv_stream(["id", "name", "username", "email", "whatsapp", "gender", "role", "created_at"], rows)
    resp.headers["Content-Disposition"] = 'attachment; filename="users.csv"'
    await log_admin_action(admin, "export_users_csv", "users", {"count": len(rows)})
    return resp


@api.get("/admin/payments/export.csv")
async def export_payments_csv(admin: dict = Depends(require_admin)):
    pays = await db.payments.find({}).to_list(None)
    rows = []
    for p in pays:
        sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
        user = await db.users.find_one({"_id": ObjectId(sub["user_id"])}) if sub else None
        svc = await db.services.find_one({"_id": ObjectId(sub["service_id"])}) if sub else None
        rows.append([
            str(p.get("_id")),
            (user or {}).get("name", ""), (user or {}).get("email", ""),
            (svc or {}).get("name", ""),
            p.get("period_label", "") or "",
            str(p.get("amount", 0)),
            p.get("due_date", "") or "",
            p.get("status", ""),
            "yes" if p.get("receipt") else "no",
            p.get("created_at", "") or "",
            p.get("last_reminder_at", "") or "",
        ])
    resp = _csv_stream(["id", "user_name", "user_email", "service", "period", "amount", "due_date", "status", "receipt_uploaded", "created_at", "last_reminder_at"], rows)
    resp.headers["Content-Disposition"] = 'attachment; filename="payments.csv"'
    await log_admin_action(admin, "export_payments_csv", "payments", {"count": len(rows)})
    return resp


# ---------------- Admin: Scheduler manual trigger ---------------- #
@api.post("/admin/scheduler/run-now")
async def scheduler_run_now(admin: dict = Depends(require_admin)):
    result = await _run_due_reminders(actor=admin)
    return {"ok": True, **result}


@api.post("/admin/invoices/generate-now")
async def invoices_generate_now(admin: dict = Depends(require_admin)):
    """Force-run invoice generator ignoring day-of-month check. Still idempotent per (sub, period)."""
    result = await _run_invoice_generator(actor=admin, force=True)
    return {"ok": True, **result}


@api.get("/admin/invoice-config")
async def get_invoice_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    return {
        "day_of_month": int(cfg.get("day_of_month", 1) or 1),
        "due_days": int(cfg.get("due_days", 7) or 7),
        "enabled": bool(cfg.get("enabled", True)),
    }


@api.put("/admin/invoice-config")
async def set_invoice_config(input: InvoiceConfigInput, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"key": "invoice_config"},
        {"$set": {**input.model_dump(), "key": "invoice_config"}},
        upsert=True,
    )
    await log_admin_action(admin, "update_invoice_config", "settings", input.model_dump())
    return {"ok": True}


@api.get("/admin/general-config")
async def get_general_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "general_config"}) or {}
    return {"default_new_user_password": cfg.get("default_new_user_password", "patungan123")}


@api.put("/admin/general-config")
async def set_general_config(input: GeneralConfigInput, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"key": "general_config"},
        {"$set": {**input.model_dump(), "key": "general_config"}},
        upsert=True,
    )
    await log_admin_action(admin, "update_general_config", "settings", {"password_changed": True})
    return {"ok": True}


# ---------------- Admin: Users bulk import + template ---------------- #
@api.get("/admin/users/template.csv")
async def users_import_template(admin: dict = Depends(require_admin)):
    header = ["name", "email", "username", "whatsapp", "gender", "password"]
    sample = [
        ["Budi Santoso", "budi@example.com", "budi", "628123456789", "male", ""],
        ["Ani Wijaya", "ani@example.com", "", "", "female", "mypassword"],
    ]
    resp = _csv_stream(header, sample)
    resp.headers["Content-Disposition"] = 'attachment; filename="users_template.csv"'
    return resp


class BulkUserImportInput(BaseModel):
    file_base64: str  # CSV file as data URL or raw base64
    file_name: Optional[str] = "users.csv"


@api.post("/admin/users/import")
async def import_users_csv(input: BulkUserImportInput, admin: dict = Depends(require_admin)):
    """Bulk import users from CSV. Skips rows with existing email or invalid data."""
    import base64 as _b64
    import csv as _csv
    import io as _io
    raw = input.file_base64
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        content = _b64.b64decode(raw).decode("utf-8-sig")
    except Exception:
        raise HTTPException(400, "File tidak bisa dibaca (bukan CSV UTF-8)")
    reader = _csv.DictReader(_io.StringIO(content))
    if not reader.fieldnames or "email" not in [f.lower().strip() for f in reader.fieldnames]:
        raise HTTPException(400, "Kolom 'email' wajib ada di header CSV.")
    # Normalize header keys
    def norm(k):
        return (k or "").lower().strip()
    gcfg = await db.settings.find_one({"key": "general_config"}) or {}
    default_pw = gcfg.get("default_new_user_password", "patungan123")
    created, skipped, errors = [], [], []
    for i, raw_row in enumerate(reader, start=2):  # start=2 because row 1 is header
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
            errors.append({"row": i, "reason": str(e), "email": email})
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


# ---------------- Google Auth (Emergent-managed) ---------------- #
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
class GoogleSessionInput(BaseModel):
    session_id: str


@api.post("/auth/google/exchange")
async def google_exchange(input: GoogleSessionInput, response: Response):
    """Exchange Emergent session_id for our JWT + persist session_token."""
    async with httpx.AsyncClient() as hc:
        r = await hc.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": input.session_id},
            timeout=15,
        )
    if r.status_code >= 300:
        raise HTTPException(status_code=401, detail="Google session invalid")
    data = r.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="No email from provider")
    existing = await db.users.find_one({"email": email})
    if existing is None:
        doc = {
            "email": email,
            "name": data.get("name") or email.split("@")[0],
            "username": email.split("@")[0],
            "picture": data.get("picture"),
            "google_id": data.get("id"),
            "password_hash": hash_password(secrets.token_urlsafe(24)),  # random unusable
            "role": "user",
            "extra": {},
            "auth_provider": "google",
            "created_at": now_utc().isoformat(),
        }
        result = await db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        user = doc
    else:
        # keep name/picture fresh
        updates = {"picture": data.get("picture") or existing.get("picture")}
        if data.get("id") and not existing.get("google_id"):
            updates["google_id"] = data["id"]
        await db.users.update_one({"_id": existing["_id"]}, {"$set": updates})
        user = {**existing, **updates}
    # Persist Emergent session_token (7 days)
    session_token = data.get("session_token")
    expires_at = now_utc() + timedelta(days=7)
    if session_token:
        await db.user_sessions.insert_one({
            "user_id": str(user["_id"]),
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": now_utc(),
        })
        response.set_cookie("session_token", session_token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    # Also issue our JWT so existing auth path works
    jwt_token = create_token(str(user["_id"]))
    response.set_cookie("access_token", jwt_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"user": user_out(user), "token": jwt_token}


# ---------------- Midtrans webhook (moved to routers/webhooks.py) ---------------- #


# ---------------- Referral (endpoints moved to routers/referral.py) ---------------- #


# ---------------- Onboarding checklist ---------------- #
# Moved to routers/referral.py


# ---------------- Analytics ---------------- #
# Moved to routers/analytics.py


# ---------------- Webhooks (Midtrans + Xendit) ---------------- #
# Moved to routers/webhooks.py


# ---------------- Payment config (QRIS image + Midtrans fee) ---------------- #
@api.get("/payment-config")
async def get_payment_config_public():
    """Public endpoint used by user dashboard to render QRIS + fee info."""
    cfg = await db.settings.find_one({"key": "payment_config"}) or {}
    return {
        "qris_image_base64": cfg.get("qris_image_base64"),
        "qris_notes": cfg.get("qris_notes", ""),
        "manual_bank_info": cfg.get("manual_bank_info", ""),
        "midtrans_fee_percent": float(cfg.get("midtrans_fee_percent", 5.0) or 5.0),
    }


@api.get("/admin/payment-config")
async def admin_get_payment_config(admin: dict = Depends(require_admin)):
    cfg = await db.settings.find_one({"key": "payment_config"}) or {}
    cfg.pop("_id", None)
    return {
        "qris_image_base64": cfg.get("qris_image_base64"),
        "qris_notes": cfg.get("qris_notes", ""),
        "manual_bank_info": cfg.get("manual_bank_info", ""),
        "midtrans_fee_percent": float(cfg.get("midtrans_fee_percent", 5.0) or 5.0),
    }


@api.put("/admin/payment-config")
async def admin_set_payment_config(input: PaymentConfigInput, admin: dict = Depends(require_admin)):
    payload = {k: v for k, v in input.model_dump().items() if v is not None}
    payload["key"] = "payment_config"
    await db.settings.update_one({"key": "payment_config"}, {"$set": payload}, upsert=True)
    await log_admin_action(admin, "update_payment_config", "settings", {
        "midtrans_fee_percent": payload.get("midtrans_fee_percent"),
        "qris_updated": bool(input.qris_image_base64),
    })
    return {"ok": True}


# ---------------- Admin: create additional admin ---------------- #
@api.post("/admin/create-admin")
async def admin_create_admin(input: CreateAdminInput, admin: dict = Depends(require_admin)):
    email = input.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email sudah terdaftar")
    doc = {
        "email": email,
        "password_hash": hash_password(input.password),
        "name": input.name,
        "username": input.username or email.split("@")[0],
        "role": "admin",
        "extra": {},
        "created_at": now_utc().isoformat(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    await log_admin_action(admin, "create_admin", f"user:{result.inserted_id}", {"email": email})
    return user_out(doc)



@api.post("/admin/cleanup-test-users")
async def cleanup_test_users(admin: dict = Depends(require_admin), prefix: str = "Iter"):
    """Delete non-admin users whose name matches ^{prefix}. Also removes their subs & payments."""
    q = {"role": {"$ne": "admin"}, "name": {"$regex": f"^{prefix}", "$options": "i"}}
    victims = await db.users.find(q).to_list(None)
    victim_ids = [str(v["_id"]) for v in victims]
    user_delete = await db.users.delete_many(q)
    subs = await db.subscriptions.find({"user_id": {"$in": victim_ids}}).to_list(None)
    sub_ids = [str(s["_id"]) for s in subs]
    await db.subscriptions.delete_many({"user_id": {"$in": victim_ids}})
    await db.payments.delete_many({"subscription_id": {"$in": sub_ids}})
    # Also clear referral_rewards touching them
    await db.referral_rewards.delete_many({"$or": [{"referrer_id": {"$in": victim_ids}}, {"referred_id": {"$in": victim_ids}}]})
    # Clear referred_by pointing to deleted users
    await db.users.update_many({"referred_by": {"$in": victim_ids}}, {"$set": {"referred_by": None}})
    await log_admin_action(admin, "cleanup_test_users", "users", {"prefix": prefix, "deleted": user_delete.deleted_count})
    return {"deleted_users": user_delete.deleted_count, "deleted_subscriptions": len(subs), "prefix": prefix}


# ---------------- Groups / Waitlist / Availability moved to routers/groups.py ---------------- #


# ---------------- Referral / Analytics / Webhooks moved to routers/ ---------------- #
# ---------------- Referral / Analytics / Webhooks moved to routers/ ---------------- #
app.include_router(api)

# Register split routers (must be after `api` is defined but before add_middleware)
from routers.analytics import router as analytics_router  # noqa: E402
from routers.referral import router as referral_router  # noqa: E402
from routers.webhooks import router as webhooks_router  # noqa: E402
from routers.groups import router as groups_router  # noqa: E402
app.include_router(analytics_router, prefix="/api")
app.include_router(referral_router, prefix="/api")
app.include_router(webhooks_router, prefix="/api")
app.include_router(groups_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
