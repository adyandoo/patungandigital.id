"""patungandigital.id — subscription sharing platform backend."""
import os
import io
import csv
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
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user_out(user)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


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
    role: str = "regular"  # host or regular
    start_date: datetime
    end_date: Optional[datetime] = None
    price: float
    status: str = "active"


class PaymentInput(BaseModel):
    subscription_id: str
    amount: float
    due_date: Optional[datetime] = None
    period_label: Optional[str] = None  # e.g., "Jan 2026"


class UploadReceiptInput(BaseModel):
    payment_id: str
    file_base64: str  # data:image/png;base64,....
    file_name: str


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
            await asyncio.wait_for(_scheduler_stop.wait(), timeout=3600)
        except asyncio.TimeoutError:
            continue


async def _run_due_reminders(actor: Optional[dict] = None) -> dict:
    cfg = await db.settings.find_one({"key": "reminder_config"}) or {}
    days = int(cfg.get("days_before_due", 3) or 3)
    now = now_utc()
    threshold = (now + timedelta(days=days)).isoformat()
    yesterday = (now - timedelta(hours=24)).isoformat()
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
    await log_admin_action(actor, "scheduler_run", "reminders", {"count": len(sent), "days_before_due": days})
    return {"count": len(sent), "sent": sent}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username")
    await db.services.create_index("slug", unique=True)
    await db.subscriptions.create_index("user_id")
    await db.payments.create_index("subscription_id")
    # Seed admin
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
        logger.info("Seeded admin user")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )
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
    doc = {
        "email": email,
        "password_hash": hash_password(input.password),
        "name": input.name,
        "username": input.username or email.split("@")[0],
        "whatsapp": input.whatsapp,
        "gender": input.gender,
        "role": "user",
        "extra": {},
        "created_at": now_utc().isoformat(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    token = create_token(str(result.inserted_id))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"user": user_out(doc), "token": token}


@api.post("/auth/login")
async def login(input: LoginInput, response: Response):
    email = input.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email atau password salah")
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
        u = await db.users.find_one({"_id": ObjectId(s["user_id"])})
        s["user"] = user_out(u) if u else None
        svc = await db.services.find_one({"_id": ObjectId(s["service_id"])})
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
async def admin_update_sub(sub_id: str, input: SubscriptionInput, admin: dict = Depends(require_admin)):
    doc = input.model_dump()
    doc["start_date"] = doc["start_date"].isoformat() if doc.get("start_date") else None
    doc["end_date"] = doc["end_date"].isoformat() if doc.get("end_date") else None
    await db.subscriptions.update_one({"_id": ObjectId(sub_id)}, {"$set": doc})
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
    doc["due_date"] = doc["due_date"].isoformat() if doc.get("due_date") else None
    doc["status"] = "pending"
    doc["created_at"] = now_utc().isoformat()
    doc["receipt"] = None
    result = await db.payments.insert_one(doc)
    doc["id"] = oid(result.inserted_id)
    doc.pop("_id", None)
    # Try create Xendit invoice if key exists
    xendit_key = os.environ.get("XENDIT_API_KEY", "")
    if xendit_key:
        try:
            async with httpx.AsyncClient() as hc:
                r = await hc.post(
                    "https://api.xendit.co/v2/invoices",
                    auth=(xendit_key, ""),
                    json={
                        "external_id": f"pay-{result.inserted_id}",
                        "amount": input.amount,
                        "description": input.period_label or "Subscription payment",
                    },
                    timeout=15,
                )
                if r.status_code < 300:
                    inv = r.json()
                    await db.payments.update_one({"_id": result.inserted_id}, {"$set": {"xendit_invoice_url": inv.get("invoice_url"), "xendit_invoice_id": inv.get("id")}})
                    doc["xendit_invoice_url"] = inv.get("invoice_url")
        except Exception as e:
            logger.warning(f"Xendit invoice failed: {e}")
    return doc


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
    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": {"receipt": receipt, "status": "review"}})
    return {"ok": True, "receipt": receipt}


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
    msg = msg_template.format(
        name=(user or {}).get("name", ""),
        service=(svc or {}).get("name", ""),
        period=p.get("period_label", ""),
        due_date=p.get("due_date", ""),
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

    await db.payments.update_one({"_id": ObjectId(payment_id)}, {"$set": {"last_reminder_at": now_utc().isoformat()}})
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


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
