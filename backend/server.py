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
try:
    from zoneinfo import ZoneInfo
except ImportError:  # py<3.9 fallback
    ZoneInfo = None
try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    relativedelta = None

WIB = ZoneInfo("Asia/Jakarta") if ZoneInfo else timezone(timedelta(hours=7))


def now_wib() -> datetime:
    return now_utc().astimezone(WIB)


def add_months(dt: datetime, months: int) -> datetime:
    """Add N months to a datetime, preserving day of month where possible."""
    if relativedelta:
        return dt + relativedelta(months=months)
    # Fallback: naive month arithmetic
    y, m = dt.year, dt.month + months
    while m > 12:
        m -= 12; y += 1
    while m < 1:
        m += 12; y -= 1
    from calendar import monthrange
    day = min(dt.day, monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)

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
mongo_url = "mongodb://127.0.0.1:27017"
client = AsyncIOMotorClient(mongo_url)
db = client["patungan_db"]

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
    {"tier": 1, "referrals": 10, "free_months": 1, "label": "Tier 1"},
    {"tier": 2, "referrals": 15, "free_months": 2, "label": "Tier 2"},   # cumulative 3 free months
    {"tier": 3, "referrals": 45, "free_months": 5, "label": "Tier 3"},   # cumulative 8 free months
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


async def auto_assign_group_for_sub(sub_id: str) -> Optional[str]:
    """When a payment goes paid and the sub isn't in a group yet, place it in the first
    group of its service that has an open slot for the sub's role.
    If all groups are full, auto-create a new group inheriting capacity from the service.
    Returns the group_id chosen or None if impossible."""
    if not ObjectId.is_valid(sub_id):
        return None
    sub = await db.subscriptions.find_one({"_id": ObjectId(sub_id)})
    if not sub or sub.get("group_id"):
        return sub.get("group_id") if sub else None
    service_id = sub.get("service_id")
    role = sub.get("role", "regular")
    if not service_id:
        return None
    # Find first group with open slot for this role (skip paused/expired groups)
    groups = await db.groups.find({
        "service_id": service_id,
        "active": True,
        "$or": [{"status": {"$in": ["active", None]}}, {"status": {"$exists": False}}],
    }).sort("created_at", 1).to_list(None)
    chosen = None
    for g in groups:
        gid = str(g["_id"])
        subs = await db.subscriptions.find({"group_id": gid, "status": "active"}).to_list(None)
        filled = sum(1 for x in subs if x.get("role") == role)
        capacity = g["host_slots"] if role == "host" else g["regular_slots"]
        if filled < capacity:
            chosen = gid
            break
    if not chosen:
        # Auto-create a new group inheriting service defaults
        svc = await db.services.find_one({"_id": ObjectId(service_id)})
        if not svc:
            return None
        idx = await db.groups.count_documents({"service_id": service_id}) + 1
        new_group = {
            "service_id": service_id,
            "name": f"{svc.get('name', 'Group')} — Grup {idx}",
            "host_slots": int(svc.get("default_host_slots", 1) or 1),
            "regular_slots": int(svc.get("default_regular_slots", 4) or 4),
            "active": True,
            "status": "active",
            "auto_created": True,
            "created_at": now_utc().isoformat(),
        }
        r = await db.groups.insert_one(new_group)
        chosen = str(r.inserted_id)
        await log_admin_action(None, "auto_create_group", f"group:{chosen}",
                               {"service_id": service_id, "reason": "no_slot_available"})
    await db.subscriptions.update_one(
        {"_id": ObjectId(sub_id)},
        {"$set": {"group_id": chosen}},
    )
    await log_admin_action(None, "auto_assign_group", f"subscription:{sub_id}",
                           {"group_id": chosen, "role": role})
    return chosen


async def extend_subscription_from_payment(payment_id: str):
    """When a payment transitions to 'paid', extend the subscription's active period.
    - start_date = first_paid_at (only set once)
    - end_date = max(existing end_date if still in future, now) + duration_months
    Idempotent: safe to call multiple times for the same payment (uses payment.applied_to_sub_at flag)."""
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not p or p.get("status") != "paid":
        return
    if p.get("applied_to_sub_at"):
        return  # already extended
    sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
    if not sub:
        return
    now = now_utc()
    duration = int(p.get("duration_months", 1) or 1)
    # start_date
    start = sub.get("start_date")
    if isinstance(start, str):
        try: start = datetime.fromisoformat(start)
        except Exception: start = None
    if isinstance(start, datetime) and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if not start or start > now:
        start = now
    # existing end_date
    end = sub.get("end_date")
    if isinstance(end, str):
        try: end = datetime.fromisoformat(end)
        except Exception: end = None
    if isinstance(end, datetime) and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    base = end if (end and end > now) else start
    new_end = add_months(base, duration)
    await db.subscriptions.update_one(
        {"_id": sub["_id"]},
        {"$set": {
            "start_date": start.isoformat(),
            "end_date": new_end.isoformat(),
            "status": "active" if sub.get("status") != "active" else sub.get("status"),
        }},
    )
    # Auto-assign to group if user has no group yet
    if not sub.get("group_id"):
        try:
            await auto_assign_group_for_sub(str(sub["_id"]))
        except Exception:
            logger.exception("auto-assign group failed")
    await db.payments.update_one(
        {"_id": ObjectId(payment_id)},
        {"$set": {"applied_to_sub_at": now.isoformat(), "duration_applied": duration}},
    )


async def revert_subscription_extension(payment_id: str):
    """If admin flips a paid payment back (refund/reject), undo the extension."""
    p = await db.payments.find_one({"_id": ObjectId(payment_id)})
    if not p or not p.get("applied_to_sub_at"):
        return
    sub = await db.subscriptions.find_one({"_id": ObjectId(p["subscription_id"])})
    if not sub:
        return
    duration = int(p.get("duration_applied", p.get("duration_months", 1)) or 1)
    end = sub.get("end_date")
    if isinstance(end, str):
        try: end = datetime.fromisoformat(end)
        except Exception: end = None
    if isinstance(end, datetime):
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        new_end = add_months(end, -duration)
        await db.subscriptions.update_one(
            {"_id": sub["_id"]},
            {"$set": {"end_date": new_end.isoformat()}},
        )
    await db.payments.update_one(
        {"_id": ObjectId(payment_id)},
        {"$unset": {"applied_to_sub_at": "", "duration_applied": ""}},
    )


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
    duration_months: int = Field(default=1, ge=1, le=24)


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
    duration_months: Optional[int] = Field(default=None, ge=1, le=24)


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
    duration_months: int = Field(default=1, ge=1, le=24)


class UploadReceiptInput(BaseModel):
    file_base64: str  # data:image/png;base64,....
    file_name: str


class ChooseMethodInput(BaseModel):
    method: str  # 'qris' or 'midtrans'


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class AdminResetPasswordInput(BaseModel):
    notify_email: bool = True


class PaymentConfigInput(BaseModel):
    qris_image_base64: Optional[str] = None  # data URL
    qris_notes: Optional[str] = ""
    midtrans_fee_percent: float = Field(default=5.0, ge=0, le=100)
    manual_bank_info: Optional[str] = ""


class InvoiceConfigInput(BaseModel):
    day_of_month: int = Field(default=1, ge=1, le=28)
    due_days: int = Field(default=7, ge=1, le=60)
    enabled: bool = True
    expiry_warning_days: int = Field(default=7, ge=1, le=30)


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
    reminder_message: Optional[str] = "Halo {name}, tagihan {service} untuk {period} akan jatuh tempo pada {due_date}. Jumlah: Rp {amount}."


class TestimonialInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=10, max_length=500)


class TestimonialUpdateInput(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = Field(default=None, min_length=10, max_length=500)


class TestimonialAdminAction(BaseModel):
    status: Optional[str] = None  # 'approved' | 'rejected' | 'pending'
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = Field(default=None, min_length=10, max_length=500)


class ProfilePicInput(BaseModel):
    profile_picture_base64: Optional[str] = None  # data URL or null to clear


class RenewInput(BaseModel):
    duration_months: Optional[int] = Field(default=None, ge=1, le=24)


class VoucherCreate(BaseModel):
    code: Optional[str] = None  # auto-generate if not provided
    description: str = Field(default="", max_length=200)
    discount_amount: int = Field(default=0, ge=0)  # flat discount in Rp
    discount_percent: float = Field(default=0.0, ge=0, le=100)  # percentage
    max_uses: int = Field(default=1, ge=1, le=10000)
    valid_days: int = Field(default=30, ge=1, le=365)  # validity in days from creation
    applies_to_user_id: Optional[str] = None  # null = global voucher
    source: str = Field(default="admin_manual", max_length=50)  # admin_manual, leaderboard, referral, etc.


class VoucherUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=200)
    discount_amount: Optional[int] = Field(default=None, ge=0)
    discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    max_uses: Optional[int] = Field(default=None, ge=1, le=10000)
    valid_until: Optional[datetime] = None
    status: Optional[str] = None  # 'active' | 'disabled'
    applies_to_user_id: Optional[str] = None


class VoucherRedeemInput(BaseModel):
    code: str


class VoucherApplyInput(BaseModel):
    code: str


class AboutInput(BaseModel):
    hero_title: str = Field(min_length=1, max_length=120)
    story: str = Field(min_length=1, max_length=4000)
    mission: Optional[str] = Field(default="", max_length=2000)
    contact_email: Optional[str] = ""
    contact_whatsapp: Optional[str] = ""
    contact_address: Optional[str] = ""


class BlogPostInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = None  # auto-generated if not provided
    excerpt: Optional[str] = Field(default="", max_length=300)
    content: str = Field(min_length=1)  # markdown
    cover_image_base64: Optional[str] = None
    tags: List[str] = []
    published: bool = False


class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    slug: Optional[str] = None
    excerpt: Optional[str] = Field(default=None, max_length=300)
    content: Optional[str] = None
    cover_image_base64: Optional[str] = None
    tags: Optional[List[str]] = None
    published: Optional[bool] = None


class AnnouncementInput(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    body: str = Field(min_length=1, max_length=2000)
    target: str = Field(default="all")  # 'all' | 'service_ids'
    service_ids: List[str] = []
    severity: str = Field(default="info")  # 'info' | 'warning' | 'critical'
    expires_at: Optional[datetime] = None


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=140)
    body: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    target: Optional[str] = None
    service_ids: Optional[List[str]] = None
    severity: Optional[str] = None
    expires_at: Optional[datetime] = None


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
            await _retry_pending_welcome_emails()
        except Exception as e:
            logger.warning(f"welcome-email retry tick failed: {e}")
        try:
            await _run_monthly_leaderboard_prizes()
        except Exception as e:
            logger.warning(f"leaderboard prize tick failed: {e}")
        try:
            await asyncio.wait_for(_scheduler_stop.wait(), timeout=3600)
        except asyncio.TimeoutError:
            continue


async def _run_invoice_generator(actor: Optional[dict] = None, force: bool = False) -> dict:
    """Generate invoices for active subscriptions on configured day of month (WIB).
    Idempotent: skips if a payment for (subscription_id, period_label) already exists.
    Uses last_run_period_label to short-circuit re-runs within same period."""
    cfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    if not cfg.get("enabled", True) and not force:
        return {"count": 0, "skipped": "disabled"}
    day = int(cfg.get("day_of_month", 1) or 1)
    due_days = int(cfg.get("due_days", 7) or 7)
    now = now_utc()
    now_local = now.astimezone(WIB)
    period_label = now_local.strftime("%b %Y")  # e.g. "Feb 2026" — based on Jakarta calendar
    if not force:
        if now_local.day != day:
            return {"count": 0, "skipped": f"not scheduled day (WIB today={now_local.day}, target={day})"}
        # Short-circuit: don't rescan every hour on the trigger day
        if cfg.get("last_run_period_label") == period_label:
            return {"count": 0, "skipped": f"already ran for period {period_label}"}
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
            "duration_months": int(sub.get("duration_months", 1) or 1),
        }
        res = await db.payments.insert_one(doc)
        created.append(str(res.inserted_id))
    # Update last_run marker (regardless of force so future ticks still short-circuit)
    await db.settings.update_one(
        {"key": "invoice_config"},
        {"$set": {"last_run_period_label": period_label, "last_run_at": now.isoformat()}},
        upsert=True,
    )
    await log_admin_action(actor, "invoice_generator_run", "payments", {
        "period": period_label, "created": len(created), "skipped": len(skipped), "forced": force, "wib_day": now_local.day,
    })
    return {"count": len(created), "created": created, "skipped": len(skipped), "period": period_label, "timezone": "Asia/Jakarta"}


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
            sent.append({"payment_id": str(p["_id"]), **{k: r.get(k) for k in ("email_sent", "mocked")}})
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
    # referral_code unique but only where field is a real string.
    # (sparse=True incorrectly treats null as present → causes duplicate-null collisions.)
    try:
        existing = await db.users.index_information()
        if "referral_code_1" in existing and existing["referral_code_1"].get("sparse"):
            await db.users.drop_index("referral_code_1")
        await db.users.create_index(
            "referral_code", unique=True,
            partialFilterExpression={"referral_code": {"$type": "string"}},
        )
    except Exception as e:
        logger.warning(f"Could not (re)create referral_code index: {e}")
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
    await db.referral_rewards.create_index("referrer_id")
    # TTL index: auto-delete expired verification tokens 24h after expiry.
    # `expireAfterSeconds=86400` = document is deleted 1 day AFTER the `expires_at` datetime.
    try:
        await db.email_verifications.create_index("expires_at", expireAfterSeconds=86400)
    except Exception as e:
        logger.warning(f"Could not create TTL index on email_verifications.expires_at: {e}")
    try:
        await db.password_resets.create_index("expires_at", expireAfterSeconds=86400)
    except Exception as e:
        logger.warning(f"Could not create TTL index on password_resets.expires_at: {e}")
    # Voucher indexes
    try:
        await db.vouchers.create_index("code", unique=True)
    except Exception as e:
        logger.warning(f"Could not create voucher code index: {e}")
    try:
        await db.vouchers.create_index("applies_to_user_id")
        await db.voucher_redemptions.create_index("user_id")
        await db.voucher_redemptions.create_index("voucher_id")
    except Exception as e:
        logger.warning(f"Voucher redemption index failed: {e}")
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
    # Ensure unique index on blog_posts.slug
    try:
        await db.blog_posts.create_index("slug", unique=True)
    except Exception as e:
        logger.warning(f"blog_posts slug index: {e}")
    # Seed default reminder config
    if not await db.settings.find_one({"key": "reminder_config"}):
        await db.settings.insert_one({
            "key": "reminder_config",
            "days_before_due": 3,
            "enable_email": True,
            "reminder_message": "Halo {name}, tagihan {service} untuk {period} akan jatuh tempo pada {due_date}. Jumlah: Rp {amount}.",
        })
    # Ensure invoice_config has expiry_warning_days field
    await db.settings.update_one(
        {"key": "invoice_config", "expiry_warning_days": {"$exists": False}},
        {"$set": {"expiry_warning_days": 7}},
    )
    # Migration: drop enable_whatsapp field if present
    await db.settings.update_one(
        {"key": "reminder_config", "enable_whatsapp": {"$exists": True}},
        {"$unset": {"enable_whatsapp": ""}},
    )
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
async def _send_verification_email(user_id: str, email: str, name: str) -> dict:
    """Generate token, save it, send email. Returns {mocked, sent, token(for tests)}."""
    token = secrets.token_urlsafe(32)
    await db.email_verifications.insert_one({
        "user_id": user_id,
        "email": email,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "expires_at": now_utc() + timedelta(hours=24),
        "used": False,
        "created_at": now_utc(),
    })
    frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
    verify_url = f"{frontend}/verify-email?token={token}"
    html = f"""
    <h2>Verifikasi email — patungandigital.id</h2>
    <p>Halo {name},</p>
    <p>Klik tombol di bawah untuk memverifikasi email kamu. Link berlaku 24 jam.</p>
    <p><a href="{verify_url}" style="background:#FF3B30;color:#fff;padding:12px 20px;text-decoration:none;font-weight:bold;border:2px solid #000;">Verifikasi Email</a></p>
    <p>Atau salin URL ini: <code>{verify_url}</code></p>
    <p>Jika kamu tidak mendaftar, abaikan email ini.</p>
    """
    result = await _send_email(email, "Verifikasi Email — patungandigital.id", html)
    # For dev/test: also include raw token in log so we can complete flow without SendGrid
    if result.get("mocked"):
        logger.info(f"[MOCK VERIFY EMAIL] token for {email}: {token}")
    return {**result, "verify_url": verify_url}


async def _send_welcome_email(email: str, name: str, referral_code: str) -> dict:
    """Send a branded welcome email after email verification.
    Includes onboarding link, subscribe instructions, and referral code with share buttons."""
    frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
    dashboard_url = f"{frontend}/dashboard"
    home_url = f"{frontend}/"
    ref_link = f"{frontend}/register?ref={referral_code}" if referral_code else frontend
    # WhatsApp share message
    wa_text = (
        f"Halo! Aku pakai patungandigital.id buat langganan premium (YouTube, Netflix, Spotify) "
        f"harga hemat lewat sistem patungan. Daftar pakai kode referralku: *{referral_code}* "
        f"biar dapet bonus. Link: {ref_link}"
    )
    from urllib.parse import quote
    wa_url = f"https://wa.me/?text={quote(wa_text)}"

    display_name = name or "Sahabat Patungan"
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#FFF8EC;padding:0;color:#0A0A0A;">
      <div style="background:#0A0A0A;padding:24px;text-align:left;border-bottom:4px solid #FF3B30;">
        <h1 style="color:#FFF8EC;margin:0;font-size:24px;letter-spacing:-0.5px;">patungandigital.id</h1>
        <p style="color:#FFC93C;margin:6px 0 0;font-size:13px;font-weight:600;">Langganan Premium, Patungan Bareng.</p>
      </div>

      <div style="padding:32px 24px;">
        <h2 style="font-size:22px;margin:0 0 12px;line-height:1.3;">Halo {display_name}, akunmu sudah aktif! 🎉</h2>
        <p style="font-size:15px;line-height:1.6;margin:0 0 20px;color:#333;">
          Selamat datang di <strong>patungandigital.id</strong> — platform patungan legal untuk layanan digital premium.
          Sekarang kamu bisa mulai berlangganan YouTube, Netflix, Spotify, dan lainnya dengan harga jauh lebih hemat.
        </p>

        <div style="background:#fff;border:2px solid #0A0A0A;padding:20px;margin:24px 0;">
          <h3 style="margin:0 0 12px;font-size:16px;">Cara Mulai Berlangganan:</h3>
          <ol style="margin:0;padding-left:20px;font-size:14px;line-height:1.8;color:#333;">
            <li>Login ke dashboard kamu</li>
            <li>Pilih layanan yang mau dilanggan (YouTube / Netflix / Spotify / dll)</li>
            <li>Pilih durasi langganan (1, 3, 6, atau 12 bulan)</li>
            <li>Selesaikan pembayaran (QRIS manual atau otomatis via Midtrans)</li>
            <li>Admin akan assign kamu ke grup & kirim kredensial akses via dashboard</li>
          </ol>
        </div>

        <div style="text-align:center;margin:28px 0;">
          <a href="{dashboard_url}" style="background:#FF3B30;color:#fff;padding:14px 28px;text-decoration:none;font-weight:bold;border:3px solid #0A0A0A;display:inline-block;font-size:15px;">Ke Dashboard Saya →</a>
        </div>

        <div style="background:#FFC93C;border:3px solid #0A0A0A;padding:20px;margin:32px 0 24px;">
          <p style="margin:0 0 6px;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Kode Referral Kamu</p>
          <p style="margin:0 0 12px;font-size:32px;font-weight:900;letter-spacing:2px;color:#0A0A0A;font-family:'Courier New',monospace;">{referral_code or '—'}</p>
          <p style="margin:0 0 16px;font-size:13px;line-height:1.5;color:#0A0A0A;">
            Bagikan kode ini ke teman. Setiap teman yang berhasil berlangganan pakai kode kamu, kamu dapat kredit bonus yang bisa dipakai untuk langganan berikutnya.
          </p>
          <div style="display:block;">
            <a href="{wa_url}" style="background:#25D366;color:#fff;padding:10px 18px;text-decoration:none;font-weight:bold;border:2px solid #0A0A0A;display:inline-block;font-size:13px;margin:4px 6px 4px 0;">Share via WhatsApp</a>
            <a href="{ref_link}" style="background:#fff;color:#0A0A0A;padding:10px 18px;text-decoration:none;font-weight:bold;border:2px solid #0A0A0A;display:inline-block;font-size:13px;margin:4px 0;">Salin Link Referral</a>
          </div>
        </div>

        <p style="font-size:13px;color:#666;line-height:1.6;margin:24px 0 0;border-top:1px solid #ddd;padding-top:16px;">
          Butuh bantuan? Balas email ini atau hubungi admin lewat WhatsApp yang tertera di website.
          <br/>Sampai jumpa di dashboard!
        </p>
      </div>

      <div style="background:#0A0A0A;padding:16px 24px;text-align:center;">
        <p style="margin:0;color:#FFF8EC;font-size:12px;">
          <a href="{home_url}" style="color:#FFC93C;text-decoration:none;">patungandigital.id</a>
          &nbsp;·&nbsp; Langganan legal · Patungan hemat
        </p>
      </div>
    </div>
    """
    result = await _send_email(email, "Selamat datang di patungandigital.id 🎉", html)
    return result


async def _retry_pending_welcome_emails(max_batch: int = 20) -> dict:
    """Background retry: find verified users whose welcome email hasn't been sent yet
    (SendGrid failed on first attempt) and retry up to 3 times. Runs every scheduler tick."""
    # Query: verified AND welcome_email_sent != True AND retries < 3 AND email_verified_at < now - 5min
    cutoff = now_utc() - timedelta(minutes=5)
    q = {
        "email_verified": True,
        "welcome_email_sent": {"$ne": True},
        "$or": [
            {"welcome_email_retries": {"$exists": False}},
            {"welcome_email_retries": {"$lt": 3}},
        ],
    }
    stats = {"attempted": 0, "sent": 0, "failed": 0, "given_up": 0}
    async for u in db.users.find(q).limit(max_batch):
        # Skip if verified too recently — main verify handler probably still in-flight
        verified_at = u.get("email_verified_at")
        if isinstance(verified_at, str):
            try:
                verified_at = datetime.fromisoformat(verified_at)
            except Exception:
                verified_at = None
        if isinstance(verified_at, datetime):
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            if verified_at > cutoff:
                continue
        stats["attempted"] += 1
        try:
            if not u.get("referral_code"):
                await ensure_referral_code(str(u["_id"]))
                u = await db.users.find_one({"_id": u["_id"]})
            res = await _send_welcome_email(u.get("email", ""), u.get("name", ""), u.get("referral_code", ""))
            if res.get("sent") or res.get("mocked"):
                await db.users.update_one(
                    {"_id": u["_id"]},
                    {"$set": {"welcome_email_sent": True, "welcome_email_sent_at": now_utc().isoformat()}},
                )
                stats["sent"] += 1
            else:
                retries = int(u.get("welcome_email_retries", 0) or 0) + 1
                update = {"welcome_email_retries": retries, "welcome_email_last_retry_at": now_utc().isoformat()}
                if retries >= 3:
                    update["welcome_email_given_up"] = True
                    stats["given_up"] += 1
                await db.users.update_one({"_id": u["_id"]}, {"$set": update})
                stats["failed"] += 1
        except Exception as e:
            logger.warning(f"welcome retry failed for {u.get('email')}: {e}")
            retries = int(u.get("welcome_email_retries", 0) or 0) + 1
            await db.users.update_one({"_id": u["_id"]}, {"$set": {"welcome_email_retries": retries, "welcome_email_last_retry_at": now_utc().isoformat()}})
            stats["failed"] += 1
    if stats["attempted"]:
        logger.info(f"welcome email retry: {stats}")
    return stats


# ---------------- Monthly referral leaderboard prizes (P2) ---------------- #
# Runs on 1st day of each month WIB. Determines top-3 referrers of the previous month
# by successful referrals (referred_by=me AND first_paid_at != None in that month) and:
#   - Top 1: +1 free_months_credit
#   - Top 2 & 3: create a Rp 15,000 voucher (30-day validity), targeted to that user
LEADERBOARD_TOP1_MONTHS = 1
LEADERBOARD_TOP23_VOUCHER = 15000


async def _run_monthly_leaderboard_prizes(force: bool = False) -> dict:
    """Idempotent: uses settings.last_leaderboard_period to short-circuit re-runs."""
    now = now_utc()
    now_local = now.astimezone(WIB)
    # Only run on day 1 unless forced
    if not force and now_local.day != 1:
        return {"skipped": "not_day_1"}
    # Determine "previous month" label — e.g. if today is Feb 1, we award for Jan
    prev = (now_local.replace(day=1) - timedelta(days=1))
    period_label = prev.strftime("%Y-%m")  # "2026-01"
    cfg = await db.settings.find_one({"key": "leaderboard_state"}) or {}
    if not force and cfg.get("last_period") == period_label:
        return {"skipped": "already_ran", "period": period_label}
    # Query: referred users first_paid_at within the previous month
    month_start = prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    next_month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    # Since first_paid_at is stored as ISO string, we query by string comparison of ISO prefixes
    month_prefix = prev.strftime("%Y-%m")  # matches ISO string prefix
    referred_users = await db.users.find({
        "referred_by": {"$ne": None},
        "first_paid_at": {"$regex": f"^{month_prefix}-"},
    }).to_list(None)
    counts = {}
    for u in referred_users:
        ref = u.get("referred_by")
        if not ref:
            continue
        counts[ref] = counts.get(ref, 0) + 1
    # Sort desc by count, then by referrer_id (stable tiebreak)
    ranking = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:3]
    awards = []
    for idx, (referrer_id, count) in enumerate(ranking):
        if count < 1:  # skip if 0 successful refs
            continue
        rank = idx + 1
        if not ObjectId.is_valid(referrer_id):
            continue
        u = await db.users.find_one({"_id": ObjectId(referrer_id)})
        if not u:
            continue
        if rank == 1:
            # +1 free month
            await db.users.update_one(
                {"_id": u["_id"]},
                {"$inc": {"free_months_credit": LEADERBOARD_TOP1_MONTHS}},
            )
            await db.referral_rewards.insert_one({
                "referrer_id": referrer_id,
                "referred_id": None,
                "payment_id": None,
                "type": f"leaderboard_top1_{period_label}",
                "amount": 0,
                "created_at": now,
            })
            awards.append({"rank": 1, "referrer_id": referrer_id, "user_email": u.get("email"), "prize": f"+{LEADERBOARD_TOP1_MONTHS} bulan gratis", "count": count})
        else:
            # Rank 2 or 3: create a Rp 15,000 voucher targeted to this user
            from routers.vouchers import _gen_voucher_code
            code = _gen_voucher_code(10)
            # ensure unique
            while await db.vouchers.find_one({"code": code}):
                code = _gen_voucher_code(10)
            voucher_doc = {
                "code": code,
                "description": f"Hadiah Leaderboard {period_label} — peringkat {rank}",
                "discount_amount": LEADERBOARD_TOP23_VOUCHER,
                "discount_percent": 0.0,
                "max_uses": 1,
                "used_count": 0,
                "valid_until": now + timedelta(days=60),
                "applies_to_user_id": referrer_id,
                "source": f"leaderboard_top{rank}",
                "status": "active",
                "created_at": now,
                "created_by": "system",
            }
            await db.vouchers.insert_one(voucher_doc)
            await db.referral_rewards.insert_one({
                "referrer_id": referrer_id,
                "referred_id": None,
                "payment_id": None,
                "type": f"leaderboard_top{rank}_{period_label}",
                "amount": LEADERBOARD_TOP23_VOUCHER,
                "voucher_code": code,
                "created_at": now,
            })
            awards.append({"rank": rank, "referrer_id": referrer_id, "user_email": u.get("email"), "prize": f"Voucher {code} - Rp {LEADERBOARD_TOP23_VOUCHER:,}", "count": count, "voucher_code": code})
    # Record run
    await db.settings.update_one(
        {"key": "leaderboard_state"},
        {"$set": {"key": "leaderboard_state", "last_period": period_label, "last_run_at": now.isoformat(), "last_awards": awards}},
        upsert=True,
    )
    await log_admin_action(None, "leaderboard_prizes_awarded", f"period:{period_label}", {"awards": awards})
    logger.info(f"Leaderboard prizes awarded for {period_label}: {len(awards)} winner(s)")
    return {"period": period_label, "awards": awards, "count": len(awards)}


class ResendVerificationInput(BaseModel):
    email: EmailStr


class VerifyEmailInput(BaseModel):
    token: str


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
        "referral_credit": 0,
        "email_verified": False,
        "auth_provider": "manual",
        "created_at": now_utc().isoformat(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    # generate referral code
    await ensure_referral_code(str(result.inserted_id))
    # Send verification email (do NOT auto-login)
    email_res = await _send_verification_email(str(result.inserted_id), email, input.name)
    return {
        "ok": True,
        "message": "Akun dibuat. Cek inbox untuk verifikasi email. Link berlaku 24 jam.",
        "email_verification_sent": True,
        "email_mocked": email_res.get("mocked", False),
    }


@api.post("/auth/verify-email")
async def verify_email(input: VerifyEmailInput, response: Response):
    th = hashlib.sha256(input.token.encode()).hexdigest()
    # Idempotent lookup: accept token even if already used, so long as it belongs to a real user
    # and hasn't expired. This handles React StrictMode double-invocation and email-client
    # link prefetchers (Gmail, corporate scanners) that hit the endpoint multiple times.
    rec = await db.email_verifications.find_one({"token_hash": th})
    if not rec:
        raise HTTPException(400, "Token tidak valid.")
    exp = rec.get("expires_at")
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not exp or exp < now_utc():
        raise HTTPException(400, "Token kadaluarsa. Minta link verifikasi baru.")
    # Mark user verified (idempotent — no-op if already verified)
    await db.users.update_one(
        {"_id": ObjectId(rec["user_id"])},
        {"$set": {"email_verified": True, "email_verified_at": now_utc().isoformat()}},
    )
    if not rec.get("used"):
        await db.email_verifications.update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": now_utc()}})
    user = await db.users.find_one({"_id": ObjectId(rec["user_id"])})
    # Ensure referral code exists so we can include it in the welcome email
    if not user.get("referral_code"):
        await ensure_referral_code(str(user["_id"]))
        user = await db.users.find_one({"_id": ObjectId(rec["user_id"])})
    # Send welcome email (idempotent flag — only send once per user)
    if not user.get("welcome_email_sent"):
        try:
            await _send_welcome_email(
                user.get("email", ""),
                user.get("name", ""),
                user.get("referral_code", ""),
            )
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"welcome_email_sent": True, "welcome_email_sent_at": now_utc().isoformat()}},
            )
        except Exception as e:
            logger.warning(f"Welcome email send failed for {user.get('email')}: {e}")
    # Auto-login on successful verification
    token = create_token(rec["user_id"])
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    await log_admin_action(None, "email_verified", f"user:{rec['user_id']}", {"email": rec.get("email")})
    return {"ok": True, "user": user_out(user), "token": token}


@api.post("/auth/resend-verification")
async def resend_verification(input: ResendVerificationInput):
    """Regenerate + email a fresh verification link. Rate-limited: 1 per 3 min per email."""
    email = input.email.lower()
    # Rate-limit
    recent = await db.email_verifications.find_one({
        "email": email,
        "created_at": {"$gte": now_utc() - timedelta(minutes=3)},
    })
    if recent:
        # Uniform response — do NOT expose rate_limited to prevent email enumeration
        return {"ok": True, "message": "Jika email terdaftar dan belum diverifikasi, kami sudah mengirim link baru."}
    user = await db.users.find_one({"email": email})
    if user and not user.get("email_verified"):
        await _send_verification_email(str(user["_id"]), email, user.get("name", ""))
    # Uniform response — no enumeration
    return {"ok": True, "message": "Jika email terdaftar dan belum diverifikasi, kami sudah mengirim link baru."}


@api.post("/auth/login")
async def login(input: LoginInput, response: Response):
    email = input.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    # Block unverified manual signups (Google users are auto-verified; legacy users without flag pass through)
    if user.get("auth_provider") == "manual" and user.get("email_verified") is False:
        raise HTTPException(status_code=403, detail="Email belum diverifikasi. Cek inbox untuk link verifikasi atau minta ulang.")
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


async def _send_email(to_email: str, subject: str, html: str) -> dict:
    """Send transactional email via SendGrid. Returns {sent, mocked, error}."""
    if not os.environ.get("SENDGRID_API_KEY"):
        logger.info(f"[MOCK EMAIL] to={to_email} subject={subject}\n{html[:200]}")
        return {"sent": False, "mocked": True}
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        m = Mail(
            from_email=os.environ.get("SENDGRID_FROM_EMAIL"),
            to_emails=to_email,
            subject=subject,
            html_content=html,
        )
        await asyncio.get_event_loop().run_in_executor(None, lambda: SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(m))
        return {"sent": True, "mocked": False}
    except Exception as e:
        logger.warning(f"SendGrid failed: {e}")
        return {"sent": False, "error": str(e)}


@api.post("/auth/forgot-password")
async def forgot_password(input: ForgotPasswordInput):
    """Generate a 1-hour reset token and email it. Always returns 200 to avoid enumeration.
    Rate-limited: max 1 token per email per 5 minutes."""
    email = input.email.lower()
    # Rate-limit check
    recent = await db.password_resets.find_one({
        "email": email,
        "created_at": {"$gte": now_utc() - timedelta(minutes=5)},
    })
    if recent:
        return {"ok": True, "message": "Jika email terdaftar, kami sudah mengirim link reset.", "rate_limited": True}
    user = await db.users.find_one({"email": email})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_resets.insert_one({
            "user_id": str(user["_id"]),
            "email": email,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": now_utc() + timedelta(hours=1),
            "used": False,
            "created_at": now_utc(),
        })
        frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        reset_url = f"{frontend}/reset-password?token={token}"
        html = f"""
        <h2>Reset Password patungandigital.id</h2>
        <p>Halo {user.get('name','')},</p>
        <p>Klik link di bawah untuk mengatur password baru. Link berlaku 1 jam.</p>
        <p><a href="{reset_url}" style="background:#FF3B30;color:#fff;padding:12px 20px;text-decoration:none;font-weight:bold;">Reset Password</a></p>
        <p>Atau salin URL: <code>{reset_url}</code></p>
        <p>Jika kamu tidak meminta reset, abaikan email ini.</p>
        """
        await _send_email(email, "Reset Password — patungandigital.id", html)
        await log_admin_action(None, "forgot_password_requested", f"user:{user['_id']}", {"email": email})
    return {"ok": True, "message": "Jika email terdaftar, kami sudah mengirim link reset."}


@api.post("/auth/reset-password")
async def reset_password(input: ResetPasswordInput):
    th = hashlib.sha256(input.token.encode()).hexdigest()
    rec = await db.password_resets.find_one({"token_hash": th, "used": False})
    if not rec:
        raise HTTPException(400, "Token tidak valid atau sudah dipakai.")
    exp = rec.get("expires_at")
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not exp or exp < now_utc():
        raise HTTPException(400, "Token kadaluarsa. Silakan minta reset baru.")
    await db.users.update_one(
        {"_id": ObjectId(rec["user_id"])},
        {"$set": {"password_hash": hash_password(input.new_password)}},
    )
    await db.password_resets.update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": now_utc()}})
    await log_admin_action(None, "password_reset_completed", f"user:{rec['user_id']}", {"email": rec.get("email")})
    return {"ok": True}


@api.patch("/auth/profile")
async def update_profile(input: UpdateProfileInput, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in input.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": updates})
    updated = await db.users.find_one({"_id": ObjectId(user["id"])})
    return user_out(updated)


@api.put("/auth/profile-picture")
async def set_profile_picture(input: ProfilePicInput, user: dict = Depends(get_current_user)):
    """Set or clear own profile picture. Client-side pre-resizes to <500KB."""
    b64 = input.profile_picture_base64
    if b64 is None:
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$unset": {"profile_picture_base64": ""}})
        u = await db.users.find_one({"_id": ObjectId(user["id"])})
        return user_out(u)
    # Basic size guard (base64 ~1.33x binary size)
    if len(b64) > 700_000:
        raise HTTPException(413, "Foto terlalu besar. Maks ~500KB setelah resize.")
    if not b64.startswith("data:image/"):
        raise HTTPException(400, "Format foto tidak valid. Harus data URL gambar.")
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"profile_picture_base64": b64}})
    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    return user_out(u)


class JoinInput(BaseModel):
    service_id: str
    duration_months: int = Field(default=1, ge=1, le=24)


@api.post("/me/subscriptions/join")
async def user_join_subscription(input: JoinInput, user: dict = Depends(get_current_user)):
    """A user selects a service + duration and initiates enrollment.
    Creates a pending subscription (no group yet) and a pending payment.
    Admin will assign a group after payment is confirmed."""
    if not ObjectId.is_valid(input.service_id):
        raise HTTPException(400, "Invalid service id")
    svc = await db.services.find_one({"_id": ObjectId(input.service_id)})
    if not svc or not svc.get("active", True):
        raise HTTPException(404, "Layanan tidak tersedia")
    min_dur = int(svc.get("min_duration_months", 1) or 1)
    if input.duration_months < min_dur:
        raise HTTPException(400, f"Durasi minimum untuk layanan ini {min_dur} bulan.")
    # Block duplicate ACTIVE/PENDING sub for the same service
    existing = await db.subscriptions.find_one({
        "user_id": user["id"],
        "service_id": input.service_id,
        "status": {"$in": ["active", "pending"]},
    })
    if existing:
        raise HTTPException(400, "Kamu sudah punya langganan aktif/pending untuk layanan ini. Lihat di tab Langganan / Pembayaran.")
    price_per_month = int(svc.get("price_regular", 0) or 0)
    # P0: 12-month annual bonus — pay 11 months, get 12 months of duration
    is_annual_bonus = (int(input.duration_months) == 12)
    billable_months = 11 if is_annual_bonus else int(input.duration_months)
    total = price_per_month * billable_months
    original_total = price_per_month * int(input.duration_months)
    now = now_utc()
    sub_doc = {
        "user_id": user["id"],
        "service_id": input.service_id,
        "plan_id": None,
        "group_id": None,
        "role": "regular",
        "start_date": None,  # activated by admin after payment
        "end_date": None,
        "price": price_per_month,
        "status": "pending",
        "duration_months": int(input.duration_months),  # user still gets 12 months of access
        "created_at": now.isoformat(),
        "self_join": True,
        "annual_bonus_applied": is_annual_bonus,
    }
    sub_res = await db.subscriptions.insert_one(sub_doc)
    sub_id = str(sub_res.inserted_id)
    # Create payment
    cfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    due_days = int(cfg.get("due_days", 7) or 7)
    period_label = now.astimezone(WIB).strftime("%b %Y")
    pay_doc = {
        "subscription_id": sub_id,
        "amount": total,
        "base_amount": total,
        "original_amount": original_total,  # for showing discount
        "period_label": period_label,
        "due_date": (now + timedelta(days=due_days)).isoformat(),
        "status": "pending",
        "created_at": now.isoformat(),
        "receipt": None,
        "payment_method": None,
        "duration_months": int(input.duration_months),
        "billable_months": billable_months,
        "self_join": True,
        "annual_bonus_applied": is_annual_bonus,
    }
    pay_res = await db.payments.insert_one(pay_doc)
    pay_doc["id"] = str(pay_res.inserted_id)
    pay_doc.pop("_id", None)
    await log_admin_action(None, "user_join", f"subscription:{sub_id}", {"user_id": user["id"], "service": svc.get("name"), "duration": input.duration_months, "annual_bonus": is_annual_bonus})
    return {"ok": True, "subscription_id": sub_id, "payment": pay_doc, "amount": total, "original_amount": original_total, "bonus_month_applied": is_annual_bonus, "service_name": svc.get("name")}


@api.post("/me/subscriptions/{sub_id}/renew")
async def user_renew_subscription(sub_id: str, input: RenewInput, user: dict = Depends(get_current_user)):
    """Create a fresh pending payment for the user's own subscription (renewal).
    Uses sub.duration_months by default, or override from input."""
    if not ObjectId.is_valid(sub_id):
        raise HTTPException(400, "Invalid subscription id")
    sub = await db.subscriptions.find_one({"_id": ObjectId(sub_id)})
    if not sub or sub.get("user_id") != user["id"]:
        raise HTTPException(404, "Langganan tidak ditemukan")
    duration = int(input.duration_months or sub.get("duration_months", 1) or 1)
    price = int(sub.get("price", 0)) * duration
    # Determine period label starting from next month after current end_date (or now)
    now = now_utc()
    end = sub.get("end_date")
    if isinstance(end, str):
        try: end = datetime.fromisoformat(end)
        except Exception: end = None
    if isinstance(end, datetime) and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start_from = end if (end and end > now) else now
    period_label = start_from.astimezone(WIB).strftime("%b %Y")
    cfg = await db.settings.find_one({"key": "invoice_config"}) or {}
    due_days = int(cfg.get("due_days", 7) or 7)
    doc = {
        "subscription_id": sub_id,
        "amount": price,
        "base_amount": price,
        "period_label": period_label,
        "due_date": now + timedelta(days=due_days),
        "status": "pending",
        "created_at": now.isoformat(),
        "receipt": None,
        "payment_method": None,
        "duration_months": duration,
        "renew_by_user": True,
    }
    r = await db.payments.insert_one(doc)
    doc["id"] = str(r.inserted_id); doc.pop("_id", None)
    if isinstance(doc.get("due_date"), datetime):
        doc["due_date"] = doc["due_date"].isoformat()
    return doc


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


@api.post("/admin/users/{user_id}/verify-email")
async def admin_manual_verify_email(user_id: str, admin: dict = Depends(require_admin)):
    """Admin manually marks a user's email as verified (bypasses token flow).
    Useful when the email verification link is broken/expired or SendGrid delivery failed.
    Also invalidates any outstanding tokens and (idempotently) sends welcome email."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "Invalid user id")
    victim = await db.users.find_one({"_id": ObjectId(user_id)})
    if not victim:
        raise HTTPException(404, "User tidak ditemukan")
    if victim.get("email_verified"):
        return {"ok": True, "already_verified": True, "user": user_out(victim)}
    await db.users.update_one(
        {"_id": victim["_id"]},
        {"$set": {"email_verified": True, "email_verified_at": now_utc().isoformat(), "email_verified_by_admin": admin["id"]}},
    )
    # Invalidate any pending verification tokens for this user
    await db.email_verifications.update_many(
        {"user_id": user_id, "used": False},
        {"$set": {"used": True, "used_at": now_utc(), "used_by": "admin"}},
    )
    # Ensure referral + welcome email (idempotent — same as verify_email path)
    victim = await db.users.find_one({"_id": victim["_id"]})
    if not victim.get("referral_code"):
        await ensure_referral_code(str(victim["_id"]))
        victim = await db.users.find_one({"_id": victim["_id"]})
    welcome_result = {"skipped": True}
    if not victim.get("welcome_email_sent"):
        try:
            welcome_result = await _send_welcome_email(victim.get("email", ""), victim.get("name", ""), victim.get("referral_code", ""))
            await db.users.update_one(
                {"_id": victim["_id"]},
                {"$set": {"welcome_email_sent": True, "welcome_email_sent_at": now_utc().isoformat()}},
            )
        except Exception as e:
            logger.warning(f"Welcome email send failed (admin manual verify) for {victim.get('email')}: {e}")
            welcome_result = {"sent": False, "error": str(e)}
    await log_admin_action(admin, "manual_email_verify", f"user:{user_id}", {"email": victim.get("email")})
    return {"ok": True, "user": user_out(victim), "welcome_email": welcome_result}


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
    # Validation: if promoting to host, ensure no existing host in target group
    if updates.get("role") == "host":
        current = await db.subscriptions.find_one({"_id": ObjectId(sub_id)})
        target_group = updates.get("group_id") or (current or {}).get("group_id")
        if target_group:
            existing_host = await db.subscriptions.find_one({
                "group_id": target_group,
                "role": "host",
                "status": "active",
                "_id": {"$ne": ObjectId(sub_id)},
            })
            if existing_host:
                raise HTTPException(400, "Grup ini sudah punya host. Hapus/turunkan host lama dulu sebelum mempromosikan user baru.")
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
    doc["duration_months"] = int(input.duration_months or 1)
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
async def admin_list_payments(auto_generated: Optional[str] = None, admin: dict = Depends(require_admin)):
    q = {}
    if auto_generated == "true":
        q["auto_generated"] = True
    elif auto_generated == "false":
        q["$or"] = [{"auto_generated": {"$ne": True}}, {"auto_generated": {"$exists": False}}]
    pays = await db.payments.find(q).to_list(None)
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
    allowed = {k: v for k, v in body.items() if k in {"status", "amount", "due_date", "period_label", "duration_months"}}
    prev = await db.payments.find_one({"_id": ObjectId(payment_id)})
    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": allowed})
    new_status = allowed.get("status")
    prev_status = (prev or {}).get("status")
    if new_status == "paid" and prev_status != "paid":
        await apply_referral_rewards_if_first_paid(payment_id)
        await extend_subscription_from_payment(payment_id)
    elif new_status and new_status != "paid" and prev_status == "paid":
        # Admin reverted a paid payment → undo sub extension
        await revert_subscription_extension(payment_id)
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
    # Trigger referral rewards + sub extension (first paid, race-safe inside helpers)
    try:
        await apply_referral_rewards_if_first_paid(payment_id)
        await extend_subscription_from_payment(payment_id)
    except Exception as e:
        logger.warning(f"post-paid apply on upload failed: {e}")
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

    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": {"last_reminder_at": now_utc()}})
    await log_admin_action(actor, "send_reminder", f"payment:{payment_id}", {"email_sent": email_sent, "mocked": mocked, "user": (user or {}).get("email")})
    return {"email_sent": email_sent, "mocked": mocked, "message": msg, "payment_id": payment_id}


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


@api.post("/admin/leaderboard/run-now")
async def admin_leaderboard_run_now(admin: dict = Depends(require_admin)):
    """Force-run the monthly leaderboard prize distribution.
    Ignores the day-of-month check but still idempotent per period via settings.last_leaderboard_period.
    Set ?force=true query param to also bypass the period check (useful for testing)."""
    force = True
    result = await _run_monthly_leaderboard_prizes(force=force)
    return {"ok": True, **result}


@api.get("/admin/leaderboard/state")
async def admin_leaderboard_state(admin: dict = Depends(require_admin)):
    """Return the last leaderboard run state (period, awards)."""
    doc = await db.settings.find_one({"key": "leaderboard_state"}) or {}
    return {
        "last_period": doc.get("last_period"),
        "last_run_at": doc.get("last_run_at"),
        "last_awards": doc.get("last_awards", []),
    }


class BulkUserImportInput(BaseModel):
    file_base64: str  # CSV file as data URL or raw base64
    file_name: Optional[str] = "users.csv"


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
            "email_verified": True,
            "email_verified_at": now_utc().isoformat(),
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


# Payment/invoice/general config endpoints moved to routers/settings.py
# Users bulk import + reset-password moved to routers/admin_users.py


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
# Late imports to avoid circular deps (these routers import from server.py)
from routers.settings import router as settings_router
from routers.admin_users import router as admin_users_router
from routers.testimonials import router as testimonials_router
from routers.cms import router as cms_router
from routers.vouchers import router as vouchers_router
app.include_router(settings_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")
app.include_router(testimonials_router, prefix="/api")
app.include_router(cms_router, prefix="/api")
app.include_router(vouchers_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
