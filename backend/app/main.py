import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from marketlens_core import __version__
from marketlens_core.db import prepare_databases
from marketlens_core.settings import Settings, get_settings

from .api.v1 import router as v1_router

log = logging.getLogger("marketlens.api")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000, tz_aware=True)
        app.state.mongo = client
        try:
            prepare_databases(client, settings)
        except PyMongoError as exc:
            log.warning("Could not prepare collections and indexes at startup: %s", type(exc).__name__)
        try:
            yield
        finally:
            client.close()

    app = FastAPI(
        title="MarketLens AI API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    allowed_origins = set(settings.cors_origin_list)

    @app.middleware("http")
    async def block_cross_site_writes(request: Request, call_next):
        """Request protection: state-changing requests must come from our own origin."""
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin not in allowed_origins and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(v1_router)
    return app


app = create_app()
