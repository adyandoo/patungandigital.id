"""Referral + Leaderboard + Onboarding router — split from server.py."""
from bson import ObjectId
from fastapi import APIRouter, Depends

from server import db, now_utc, ensure_referral_code, get_current_user, REFERRAL_REWARD, TIER_THRESHOLDS

router = APIRouter()


@router.get("/me/referral-stats")
async def my_referral_stats(user: dict = Depends(get_current_user)):
    code = user.get("referral_code")
    if not code:
        code = await ensure_referral_code(user["id"])
    invited = await db.users.count_documents({"referred_by": user["id"]})
    successful = await db.users.count_documents({"referred_by": user["id"], "first_paid_at": {"$ne": None}})
    rewards = await db.referral_rewards.find({"referrer_id": user["id"]}).to_list(None)
    total_earned = sum((r.get("amount") or 0) for r in rewards)
    referred_by_user = None
    if user.get("referred_by") and ObjectId.is_valid(user["referred_by"]):
        r = await db.users.find_one({"_id": ObjectId(user["referred_by"])})
        if r:
            referred_by_user = {"name": r.get("name"), "email": r.get("email")}
    fresh = await db.users.find_one({"_id": ObjectId(user["id"])})
    granted = fresh.get("tiers_granted", []) or []
    next_tier = next((t for t in TIER_THRESHOLDS if t["tier"] not in granted), None)
    return {
        "referral_code": code,
        "referral_credit": fresh.get("referral_credit", 0),
        "free_months_credit": fresh.get("free_months_credit", 0),
        "invited_count": invited,
        "successful_count": successful,
        "total_earned": total_earned,
        "reward_per_referral": REFERRAL_REWARD,
        "referred_by": referred_by_user,
        "tiers": TIER_THRESHOLDS,
        "tiers_granted": granted,
        "next_tier": next_tier,
    }


@router.get("/me/onboarding")
async def my_onboarding(user: dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"_id": ObjectId(user["id"])})
    invited = await db.users.count_documents({"referred_by": user["id"]})
    has_any_sub = await db.subscriptions.count_documents({"user_id": user["id"]}) > 0
    steps = [
        {"key": "signup", "label": "Buat akun", "done": True},
        {"key": "profile", "label": "Lengkapi profil (nama, WhatsApp, gender)", "done": bool(fresh.get("whatsapp") or fresh.get("gender"))},
        {"key": "first_payment", "label": "Ikut patungan pertama (pilih layanan)", "done": has_any_sub or bool(fresh.get("first_paid_at"))},
        {"key": "invite", "label": "Ajak 1 teman via kode referral", "done": invited >= 1},
        {"key": "reward", "label": "Unlock kredit Rp 10.000", "done": (fresh.get("referral_credit", 0) > 0 or fresh.get("free_months_credit", 0) > 0)},
    ]
    completed = sum(1 for s in steps if s["done"])
    return {"steps": steps, "completed": completed, "total": len(steps), "percent": int(round(completed / len(steps) * 100))}


@router.get("/leaderboard")
async def leaderboard():
    """Public leaderboard: top referrers this month + all time."""
    now = now_utc()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def rank(match_extra: dict):
        pipeline = [
            {"$match": {"referrer_id": {"$ne": None}, "referred_id": {"$ne": None}, **match_extra}},
            {"$group": {"_id": "$referrer_id", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
            {"$sort": {"count": -1, "total": -1}},
            {"$limit": 10},
        ]
        rows = await db.referral_rewards.aggregate(pipeline).to_list(None)
        result = []
        for i, r in enumerate(rows):
            uref = await db.users.find_one({"_id": ObjectId(r["_id"])}) if ObjectId.is_valid(r["_id"]) else None
            if not uref:
                continue
            result.append({
                "rank": i + 1,
                "user_id": r["_id"],
                "name": uref.get("name") or "-",
                "initials": "".join([p[0] for p in (uref.get("name") or "-").split()[:2]]).upper(),
                "count": r["count"],
                "total_earned": r["total"],
                "tiers_granted": uref.get("tiers_granted", []) or [],
            })
        return result

    monthly = await rank({"created_at": {"$gte": month_start}})
    all_time = await rank({})
    return {"monthly": monthly, "all_time": all_time, "month_label": now.strftime("%B %Y")}
