"""Analytics router — split from server.py."""
from datetime import timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends

from server import db, now_utc, require_admin

router = APIRouter()


@router.get("/admin/analytics")
async def admin_analytics(admin: dict = Depends(require_admin)):
    """Aggregate monthly revenue + revenue-per-service via single $lookup pipeline."""
    now = now_utc()
    start = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=365)).replace(day=1)

    base_pipeline = [
        {"$match": {"status": "paid"}},
        {"$addFields": {
            "created_dt": {"$cond": [{"$eq": [{"$type": "$created_at"}, "string"]},
                                     {"$dateFromString": {"dateString": "$created_at", "onError": None, "onNull": None}},
                                     "$created_at"]},
            "sub_oid": {"$toObjectId": "$subscription_id"},
        }},
        {"$lookup": {"from": "subscriptions", "localField": "sub_oid", "foreignField": "_id", "as": "sub"}},
        {"$unwind": {"path": "$sub", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {"svc_oid": {"$toObjectId": "$sub.service_id"}}},
        {"$lookup": {"from": "services", "localField": "svc_oid", "foreignField": "_id", "as": "svc"}},
        {"$unwind": {"path": "$svc", "preserveNullAndEmptyArrays": True}},
    ]

    monthly_rows = await db.payments.aggregate(base_pipeline + [
        {"$match": {"created_dt": {"$gte": start}}},
        {"$group": {"_id": {"y": {"$year": "$created_dt"}, "m": {"$month": "$created_dt"}}, "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.y": 1, "_id.m": 1}},
    ]).to_list(None)

    months = []
    cursor = start
    while cursor <= now:
        months.append({"year": cursor.year, "month": cursor.month, "revenue": 0, "count": 0})
        cursor = cursor.replace(year=cursor.year + 1, month=1) if cursor.month == 12 else cursor.replace(month=cursor.month + 1)
    for row in monthly_rows:
        y, m = row["_id"]["y"], row["_id"]["m"]
        for slot in months:
            if slot["year"] == y and slot["month"] == m:
                slot["revenue"] = row["revenue"]
                slot["count"] = row["count"]
                break
    labels_id = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    monthly = [{"label": f"{labels_id[m['month']-1]} {str(m['year'])[2:]}", "revenue": m["revenue"], "count": m["count"]} for m in months]

    by_service_rows = await db.payments.aggregate(base_pipeline + [
        {"$group": {"_id": "$svc.name", "color": {"$first": "$svc.color"}, "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"revenue": -1}},
    ]).to_list(None)
    by_service = [{"service": r["_id"] or "-", "color": r.get("color") or "#0A0A0A", "revenue": r["revenue"], "count": r["count"]} for r in by_service_rows]

    status_rows = await db.payments.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}}]).to_list(None)
    status_dist = [{"status": r["_id"], "count": r["count"], "total": r["total"]} for r in status_rows]
    total_rows = await db.payments.aggregate([{"$match": {"status": "paid"}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}]).to_list(None)
    tr = total_rows[0] if total_rows else {"total": 0, "count": 0}
    totals = {
        "total_revenue_paid": tr["total"],
        "paid_count": tr["count"],
        "avg_payment": (tr["total"] / tr["count"]) if tr["count"] else 0,
    }
    return {"monthly": monthly, "by_service": by_service, "status_distribution": status_dist, "totals": totals}
