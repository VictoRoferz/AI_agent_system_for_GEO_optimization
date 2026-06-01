"""FastAPI application entry point for the GEO Assistant backend."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import meta
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database tables on startup.
    from app.storage.db import init_db

    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="GEO Optimization Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router)

    # Routers added incrementally as features land:
    from app.api import analyze, runs, studio

    app.include_router(analyze.router)
    app.include_router(runs.router)
    app.include_router(studio.router)
    return app


app = create_app()
