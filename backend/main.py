import time
import traceback
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import ensure_database
from services import analytics
from services.ai_agent import answer_question
from services.market import (
    get_company_details,
    get_top_brokers,
    get_top_companies,
    get_top_products,
)
from services.statistics import (
    get_status_statistics,
    get_total_statistics,
    get_yearly_statistics,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Birja AI",
    description="O'zbekiston birja bitimlari bo'yicha AI yordamchi",
    version="2.0.0",
)


@app.on_event("startup")
def startup():
    # birja.duckdb yo'q bo'lsa, CSV fayllardan avtomatik yaratadi
    ensure_database()


# ------------------------------------------------------------------ umumiy

@app.get("/api/health")
def health():
    return {"success": True, "message": "Backend ishlayapti!"}


@app.get("/api/statistics")
def total_statistics():
    return {"success": True, "data": get_total_statistics()}


@app.get("/api/statistics/yearly")
def yearly_statistics():
    return {"success": True, "data": get_yearly_statistics()}


@app.get("/api/statistics/statuses")
def status_statistics():
    return {"success": True, "data": get_status_statistics()}


# --------------------------------------------------------------- dashboard

def _year_filter(year: Optional[int]):
    return {"year": year, "status_filter": "not_cancelled"} if year else {
        "status_filter": "not_cancelled"
    }


@app.get("/api/dashboard/summary")
def dashboard_summary(year: Optional[int] = Query(default=None, ge=2000, le=2100)):
    """KPI kartochkalari. Summalar bekor qilingan bitimlarsiz."""
    totals = analytics.analyze_deals(
        metrics=["deals_count", "total_amount_usd", "total_amount_uzs",
                 "avg_amount_usd", "unique_sellers", "unique_buyers"],
        filters=_year_filter(year),
    )["rows"][0]
    all_deals = analytics.analyze_deals(
        metrics=["deals_count"], filters={"year": year} if year else {}
    )["rows"][0]["deals_count"]
    cancelled = analytics.analyze_deals(
        metrics=["deals_count"],
        filters={**({"year": year} if year else {}), "status_filter": "cancelled"},
    )["rows"][0]["deals_count"]
    return {
        "success": True,
        "data": {
            **totals,
            "all_deals": all_deals,
            "cancelled_deals": cancelled,
            "cancel_rate_pct": round(cancelled / all_deals * 100, 2) if all_deals else 0,
        },
    }


@app.get("/api/dashboard/monthly")
def dashboard_monthly(year: Optional[int] = Query(default=None, ge=2000, le=2100)):
    return {"success": True, "data": analytics.monthly_trend(_year_filter(year))}


@app.get("/api/dashboard/yearly")
def dashboard_yearly():
    data = analytics.analyze_deals(
        group_by=["year"],
        metrics=["deals_count", "total_amount_usd"],
        filters={"status_filter": "not_cancelled"},
        order_by="year",
        descending=False,
    )
    return {"success": True, "data": data["rows"]}


@app.get("/api/dashboard/breakdown")
def dashboard_breakdown(
    by: Literal["region", "product", "category", "trade_type",
                "contract_type", "status"] = "region",
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Istalgan kesim bo'yicha reyting (bitimlar soni va USD summa)."""
    filters = _year_filter(year)
    if by == "status":
        filters = {"year": year} if year else {}
    data = analytics.analyze_deals(
        group_by=[by],
        metrics=["deals_count", "total_amount_usd", "total_amount_uzs"],
        filters=filters,
        order_by="total_amount_usd" if by != "status" else "deals_count",
        limit=limit,
    )
    return {"success": True, "data": data["rows"]}


@app.get("/api/dashboard/top-companies")
def dashboard_top_companies(
    side: Literal["seller", "buyer"] = "seller",
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    limit: int = Query(default=10, ge=1, le=50),
):
    column = f"{side}_name"
    data = analytics.analyze_deals(
        group_by=[column],
        metrics=["deals_count", "total_amount_usd"],
        filters=_year_filter(year),
        order_by="total_amount_usd",
        limit=limit,
    )
    return {"success": True, "data": data["rows"]}


@app.get("/api/dashboard/top-brokers")
def dashboard_top_brokers(
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Sotuvchi tomondagi brokerlar bo'yicha reyting."""
    data = analytics.analyze_deals(
        group_by=["seller_broker_name"],
        metrics=["deals_count", "total_amount_usd"],
        filters=_year_filter(year),
        order_by="total_amount_usd",
        limit=limit,
    )
    return {"success": True, "data": data["rows"]}


# ---------------------------------------------- avvalgi endpointlar (saqlangan)

@app.get("/api/companies/top")
def top_companies(limit: int = Query(default=10, ge=1, le=100)):
    return {"success": True, "data": get_top_companies(limit)}


@app.get("/api/companies/{inn}")
def company_details(inn: str):
    result = get_company_details(inn)
    if result is None:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
    return {"success": True, "data": result}


@app.get("/api/brokers/top")
def top_brokers(limit: int = Query(default=10, ge=1, le=100)):
    return {"success": True, "data": get_top_brokers(limit)}


@app.get("/api/products/top")
def top_products(limit: int = Query(default=10, ge=1, le=100)):
    return {"success": True, "data": get_top_products(limit)}


# --------------------------------------------------------------------- chat

class HistoryItem(BaseModel):
    role: Literal["user", "bot"]
    text: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    language: Literal["auto", "uz", "ru", "en"] = "auto"
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)


# Oddiy IP bo'yicha tezlik cheklovi (Gemini kvotasini himoya qilish uchun)
RATE_LIMIT = 20          # so'rov
RATE_WINDOW = 60         # soniya
_hits = defaultdict(deque)


def _check_rate_limit(ip: str):
    now = time.time()
    hits = _hits[ip]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Juda ko'p so'rov. Bir daqiqadan keyin qayta urinib ko'ring.",
        )
    hits.append(now)


@app.post("/api/chat")
def chat(request: ChatRequest, http_request: Request):
    _check_rate_limit(http_request.client.host if http_request.client else "?")
    try:
        result = answer_question(
            request.question,
            request.language,
            [item.model_dump() for item in request.history],
        )
        return {
            "success": True,
            "answer": result["answer"],
            "sources": result["sources"],
            "language": request.language,
        }
    except RuntimeError as exc:  # masalan, API kalit yo'q
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail="AI xizmatida xatolik yuz berdi. Qayta urinib ko'ring.",
        )


# ----------------------------------------------------------------- frontend

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
