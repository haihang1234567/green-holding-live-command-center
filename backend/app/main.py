from __future__ import annotations

from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .realtime import manager
from .scheduler import start_background_tasks, stop_background_tasks
from .seed import seed_database
from .routers import admin, auth, dashboard, data, integrations, mock, reports, sessions, users, webhooks

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    tasks = start_background_tasks()
    yield
    await stop_background_tasks(tasks)


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
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
    return {"status": "ok", "app": settings.app_name, "data_provider": settings.data_provider.upper(), "live_status_provider": settings.live_status_provider.upper()}


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
