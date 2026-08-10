import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.db import Base, engine, SessionLocal
from app.routers import auth, admin, team, mock, config, realtime, analytics, reports
from app.services.seed import seed_database
from app.services.mock_engine import auto_tick
from app.services.snapshot import create_due_snapshots
from app.services.sync_engine import poll_real_data
from app.services.realtime import manager

settings = get_settings()


async def background_loop():
    counter = 0
    while True:
        await asyncio.sleep(max(5, settings.mock_tick_seconds if settings.data_provider.upper() == "MOCK" else settings.poll_interval_seconds))
        db = SessionLocal()
        try:
            if settings.data_provider.upper() == "MOCK": auto_tick(db)
            else: poll_real_data(db)
            create_due_snapshots(db)
            counter += 1
            await manager.broadcast({"type": "DATA_UPDATED", "action": "BACKGROUND_TICK", "counter": counter})
        except Exception as exc: print("background loop error:", exc)
        finally: db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try: seed_database(db)
    finally: db.close()
    task = asyncio.create_task(background_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError): await task


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(team.router, prefix="/api")
app.include_router(mock.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(realtime.router)

@app.get("/api/health")
def health(): return {"ok": True, "provider": settings.data_provider.upper()}
