"""Product Explorer API. Read-only; every query runs against the requested mode's database only."""

from enum import Enum
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError

from marketlens_core.advice import buying_advice
from marketlens_core.audit import product_audit
from marketlens_core.sync import product_sync
from marketlens_core.evidence import price_evidence
from marketlens_core.forecast import product_forecast
from marketlens_core.images import attach_image_urls
from marketlens_core.explorer import CATEGORY_LABELS, filter_metadata, list_products, product_detail, product_reviews
from marketlens_core.history import HistoryError, as_of, parse_utc, product_history
from marketlens_core.settings import DataMode

router = APIRouter(prefix="/products", tags=["products"])

ProductId = Path(..., min_length=1, max_length=128, description="Product ID exactly as stored")
SortKey = Literal[
    "name_asc", "name_desc", "price_asc", "price_desc", "delivered_asc", "delivered_desc",
    "rating_desc", "discount_desc", "available_desc", "offers_desc",
]


class Availability(str, Enum):
    in_stock = "in_stock"
    limited_stock = "limited_stock"
    out_of_stock = "out_of_stock"
    unknown = "unknown"


def _db(request: Request, mode: DataMode):
    settings = request.app.state.settings
    reason = settings.mode_unavailable_reason(mode)
    if reason:
        raise HTTPException(409, reason)
    return request.app.state.mongo[settings.database_for(mode)]


def _unavailable():
    raise HTTPException(503, "The database is unavailable. Try again shortly.")


@router.get("")
def products(
    request: Request,
    mode: DataMode = Query(DataMode.DEMO),
    q: str | None = Query(None, max_length=100, description="Product ID (exact, any case) or part of the name"),
    category: str | None = Query(None),
    marketplace: list[str] | None = Query(None, description="Repeatable"),
    currency: str | None = Query(None, pattern=r"^[A-Z]{3}$", description="Required with price filters"),
    price_min_minor: int | None = Query(None, ge=0, description="Base listing price, minor units"),
    price_max_minor: int | None = Query(None, ge=0, description="Base listing price, minor units"),
    availability: list[Availability] | None = Query(None, description="Stated availability; repeatable"),
    seller_rating_min: float | None = Query(None, ge=0, le=5),
    product_rating_min: float | None = Query(None, ge=0, le=5),
    free_shipping: bool = Query(False, description="Only listings with known zero shipping"),
    condition: str | None = Query(None, max_length=40),
    discount_min: float | None = Query(None, ge=0, le=100, description="Advertised discount percent, same listing"),
    discount_max: float | None = Query(None, ge=0, le=100, description="Advertised discount percent, same listing"),
    delivered_known: bool = Query(False, description="Only listings with a confirmed delivered price (known shipping)"),
    sort: SortKey = Query("name_asc"),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(24, ge=1, le=60),
) -> dict:
    if category is not None and category not in CATEGORY_LABELS:
        raise HTTPException(422, f"Unknown category '{category}'.")
    if (price_min_minor is not None or price_max_minor is not None) and not currency:
        raise HTTPException(422, "Choose a currency for price filters; prices in different currencies aren't compared.")
    if price_min_minor is not None and price_max_minor is not None and price_min_minor > price_max_minor:
        raise HTTPException(422, "The minimum price is higher than the maximum price.")
    if discount_min is not None and discount_max is not None and discount_min > discount_max:
        raise HTTPException(422, "The minimum discount is higher than the maximum discount.")
    db = _db(request, mode)
    filters = {
        "q": q,
        "category": category,
        "marketplaces": [m for m in (marketplace or []) if m][:10],
        "currency": currency,
        "price_min": price_min_minor,
        "price_max": price_max_minor,
        "availability": [a.value for a in (availability or [])],
        "seller_rating_min": seller_rating_min,
        "product_rating_min": product_rating_min,
        "free_shipping": free_shipping,
        "condition": condition,
        "discount_min": discount_min,
        "discount_max": discount_max,
        "delivered_known": delivered_known,
    }
    try:
        result = list_products(db, filters=filters, sort=sort, page=page, page_size=page_size)
        attach_image_urls(db, result["items"], request.app.state.settings.image_hosts)
    except PyMongoError:
        _unavailable()
    return {"mode": mode.value, **result}


@router.get("/filters")
def filters(request: Request, mode: DataMode = Query(DataMode.DEMO)) -> dict:
    db = _db(request, mode)
    try:
        return {"mode": mode.value, **filter_metadata(db)}
    except PyMongoError:
        _unavailable()


@router.get("/{product_id}")
def product(request: Request, product_id: str = ProductId, mode: DataMode = Query(DataMode.DEMO)) -> dict:
    db = _db(request, mode)
    try:
        d = product_detail(db, product_id)
        if d is not None:
            attach_image_urls(db, [d["product"]], request.app.state.settings.image_hosts)
    except PyMongoError:
        _unavailable()
    if d is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **d})


@router.get("/{product_id}/history")
def history(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff, e.g. 2026-10-15T12:00:00Z; nothing later is read"),
    window: int = Query(30, description="7, 30, 90 or 180 days"),
    basis: Literal["base", "delivered"] = Query("base"),
    marketplace: str | None = Query(None, max_length=60),
) -> dict:
    db = _db(request, mode)
    try:
        h = product_history(db, product_id, cutoff=parse_utc(cutoff, "cutoff"), window_days=window, basis=basis, marketplace=marketplace)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if h is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return {"mode": mode.value, **h}


@router.get("/{product_id}/evidence")
def evidence(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff, e.g. 2026-10-31T23:59:59Z; nothing later is read"),
    window: int = Query(90, description="7, 30, 90 or 180 days"),
    basis: Literal["base", "delivered"] = Query("base"),
) -> dict:
    """Real Price Detector and Genuine Discount Score with their evidence, window, cutoff and limitations."""
    db = _db(request, mode)
    try:
        e = price_evidence(db, product_id, cutoff=parse_utc(cutoff, "cutoff"), window_days=window, basis=basis)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if e is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **e})


@router.get("/{product_id}/advice")
def advice(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff; nothing later is read"),
    window: int = Query(90, description="7, 30, 90 or 180 days"),
    basis: Literal["base", "delivered"] = Query("base"),
) -> dict:
    """Buying advice from observed history (no forecast): recommendation, confidence, reasons and disagreeing signals."""
    db = _db(request, mode)
    try:
        a = buying_advice(db, product_id, cutoff=parse_utc(cutoff, "cutoff"), window_days=window, basis=basis)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if a is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **a})


@router.get("/{product_id}/forecast")
def forecast(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff; models are trained and backtested only on data up to it"),
    basis: Literal["base", "delivered"] = Query("base"),
) -> dict:
    """7/14/30-day forecasts with chronological backtests against a baseline, plus Future Price Memory."""
    db = _db(request, mode)
    try:
        f = product_forecast(db, product_id, cutoff=parse_utc(cutoff, "cutoff"), basis=basis)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if f is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **f})


@router.get("/{product_id}/sync")
def seller_sync(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff; nothing later is read"),
    window: int = Query(90, description="7, 30, 90 or 180 days"),
) -> dict:
    """Seller synchronization between store listings: patterns worth investigating, never proof."""
    db = _db(request, mode)
    try:
        r = product_sync(db, product_id, cutoff=parse_utc(cutoff, "cutoff"), window_days=window)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if r is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **r})


@router.get("/{product_id}/audit")
def audit(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff; nothing later is read"),
    window: int = Query(90, description="7, 30, 90 or 180 days"),
) -> dict:
    """Dark-pattern audit findings with rule version, severity, confidence, evidence and benign explanations."""
    db = _db(request, mode)
    try:
        r = product_audit(db, product_id, cutoff=parse_utc(cutoff, "cutoff"), window_days=window)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if r is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **r})


@router.get("/{product_id}/as-of")
def product_as_of(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    at: str = Query(..., description="Explicit UTC time; the latest verified observation at or before it is shown"),
) -> dict:
    db = _db(request, mode)
    try:
        s = as_of(db, product_id, at=parse_utc(at, "at"))
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        _unavailable()
    if s is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return {"mode": mode.value, **s}


@router.get("/{product_id}/reviews")
def reviews(
    request: Request,
    product_id: str = ProductId,
    mode: DataMode = Query(DataMode.DEMO),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(10, ge=1, le=100),
) -> dict:
    db = _db(request, mode)
    try:
        r = product_reviews(db, product_id, page, page_size)
    except PyMongoError:
        _unavailable()
    if r is None:
        raise HTTPException(404, f"No product '{product_id}' in {mode.value.capitalize()} data.")
    return jsonable_encoder({"mode": mode.value, **r})
