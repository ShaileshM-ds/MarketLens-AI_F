from fastapi import APIRouter

from ... import auth
from . import admin_demo, admin_imports, categories, compare, dashboard, health, methodology, products, watch

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(categories.router)
router.include_router(products.router)
router.include_router(compare.router)
router.include_router(dashboard.router)
router.include_router(methodology.router)
router.include_router(watch.router)
router.include_router(auth.router)
router.include_router(admin_imports.router)
router.include_router(admin_demo.router)
