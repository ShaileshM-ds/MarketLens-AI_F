from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from marketlens_core.catalog import LAUNCH_CATEGORIES, PRODUCTS_COLLECTION
from marketlens_core.settings import DataMode

router = APIRouter(tags=["catalog"])


class CategoryOut(BaseModel):
    slug: str
    label: str
    product_count: int  # 0 means no data yet in this mode


class CategoriesOut(BaseModel):
    mode: DataMode
    categories: list[CategoryOut]


@router.get("/categories", response_model=CategoriesOut)
def list_categories(request: Request, mode: DataMode = Query(DataMode.DEMO)) -> CategoriesOut:
    settings = request.app.state.settings
    reason = settings.mode_unavailable_reason(mode)
    if reason:
        raise HTTPException(status_code=409, detail=reason)

    # Reads only the active mode's database; modes are never mixed.
    db = request.app.state.mongo[settings.database_for(mode)]
    try:
        counts = {
            doc["_id"]: doc["count"]
            for doc in db[PRODUCTS_COLLECTION].aggregate([{"$group": {"_id": "$category", "count": {"$sum": 1}}}])
        }
    except PyMongoError:
        raise HTTPException(status_code=503, detail="The database is unavailable.")

    return CategoriesOut(
        mode=mode,
        categories=[
            CategoryOut(slug=c.slug, label=c.label, product_count=counts.get(c.slug, 0)) for c in LAUNCH_CATEGORIES
        ],
    )
