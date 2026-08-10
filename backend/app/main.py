from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import Channel
from .profiled_providers import (
    DualLiveStatusProvider,
    DualTikTokAdsProvider,
    DualTikTokShopProvider,
    apply_profile_to_channel,
    profile_for_channel,
)
from .providers import ManualLiveProvider, MockLiveProvider, providers
from .realtime import manager
from .scheduler import start_background_tasks, stop_background_tasks
from .seed import seed_database
from .routers import admin, auth, dashboard, data, integrations, mock, reports, sessions, users, webhooks

settings = get_settings()


def configure_runtime_providers() -> None:
    """Select providers once at process startup.

    MOCK keeps the simulator available. TIKTOK uses two completely independent
    credential profiles. LIVE status AUTO never starts a session locally; it
    only reacts to status returned by the two configured external sources.
    """
    if settings.data_provider.upper() == "TIKTOK":
        providers.shop = DualTikTokShopProvider(settings)
        providers.ads = DualTikTokAdsProvider(settings)

    live_mode = settings.live_status_provider.upper()
    if live_mode == "AUTO":
        providers.live = DualLiveStatusProvider(settings)
    elif live_mode == "MANUAL":
        providers.live = ManualLiveProvider()
    elif live_mode == "MOCK":
        providers.live = MockLiveProvider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    configure_runtime_providers()
    with SessionLocal() as db:
        seed_database(db)
        # Copy only non-secret identifiers from environment profiles into the
        # channel table. Secrets stay exclusively in Render/server ENV.
        if settings.data_provider.upper() == "TIKTOK":
            channels = db.scalars(select(Channel).order_by(Channel.id)).all()
            for channel in channels:
                apply_profile_to_channel(channel, profile_for_channel(settings, channel))
            db.commit()
    tasks = start_background_tasks()
    yield
    await stop_background_tasks(tasks)


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, dashboard.router, sessions.router, admin.router, data.router, mock.router, integrations.router, reports.router, users.router, webhooks.router):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "2.0.0",
        "data_provider": settings.data_provider.upper(),
        "live_status_provider": settings.live_status_provider.upper(),
        "polling_interval_seconds": settings.polling_interval_seconds,
        "metric_snapshot_interval_seconds": settings.metric_snapshot_interval_seconds,
    }


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token:
        try:
            jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        except Exception:
            await websocket.close(code=4401)
            return
    elif settings.environment.lower() == "production":
        await websocket.close(code=4401)
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


frontend_dist = Path(os.getenv("FRONTEND_DIST", "/app/frontend-dist")).resolve()
assets_dir = frontend_dist / "assets"
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        candidate = (frontend_dist / full_path).resolve()
        if candidate != frontend_dist and frontend_dist in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")
