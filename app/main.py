import os

from contextlib import asynccontextmanager



from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles



from app.core.auth import decode_access_token, hash_password

from app.core.config import settings

from app.core.database import Base, async_session, engine

from app.middleware.security_headers import SecurityHeadersMiddleware

from app.repositories.platform_repository import PlatformRepository

from app.routers import (
    actions,
    agenda,
    audit,
    auth,
    catalog,
    chat,
    child_app,
    child_auth,
    children,
    dashboard,
    missions,
    notifications,
    platform,
    quizzes,
    settings as settings_router,
)

from app.services.reminders import check_agenda_reminders, check_inactivity_reminders
from app.services.snapshot_service import run_all_weekly_snapshots
from app.services.quiz_service import seed_default_templates
from app.core.migrations import run_light_migrations

from app.websocket.manager import ws_manager



scheduler = AsyncIOScheduler()





async def seed_platform_admin():

    async with async_session() as db:

        await PlatformRepository(db).seed_if_missing(

            email=settings.platform_admin_email,

            password=settings.platform_admin_password,

            name=settings.platform_admin_name,

        )

        await db.commit()





async def run_weekly_snapshots_job():
    async with async_session() as db:
        await run_all_weekly_snapshots(db)
        await db.commit()


@asynccontextmanager

async def lifespan(app: FastAPI):

    os.makedirs(settings.upload_dir, exist_ok=True)

    async with engine.begin() as conn:

        await conn.run_sync(Base.metadata.create_all)

    await run_light_migrations()

    await seed_platform_admin()
    async with async_session() as db:
        await seed_default_templates(db)
        await db.commit()

    testing = os.getenv("TESTING", "").lower() in ("1", "true", "yes")
    if not testing:
        scheduler.add_job(check_inactivity_reminders, "interval", hours=6)
        scheduler.add_job(check_agenda_reminders, "interval", hours=1)
        scheduler.add_job(run_weekly_snapshots_job, "cron", day_of_week="mon", hour=0, minute=5)
        scheduler.start()
    yield
    if not testing:
        scheduler.shutdown()





app = FastAPI(

    title="Family Mission API",

    version="2.0.0",

    description="MVC architecture: controllers → services → repositories → models",

    lifespan=lifespan,

)



app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(

    CORSMiddleware,

    allow_origins=settings.cors_origins_list,

    allow_credentials=True,

    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],

    allow_headers=["Authorization", "Content-Type"],

)



app.include_router(auth.router, prefix="/api")

app.include_router(child_auth.router, prefix="/api")

app.include_router(children.router, prefix="/api")

app.include_router(missions.router, prefix="/api")

app.include_router(catalog.router, prefix="/api")

app.include_router(actions.router, prefix="/api")

app.include_router(dashboard.router, prefix="/api")

app.include_router(settings_router.router, prefix="/api")

app.include_router(child_app.router, prefix="/api")

app.include_router(notifications.router, prefix="/api")

app.include_router(agenda.router, prefix="/api")

app.include_router(audit.router, prefix="/api")

app.include_router(platform.router, prefix="/api")
app.include_router(quizzes.router, prefix="/api")
app.include_router(chat.router, prefix="/api")



app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")





@app.get("/api/health")

async def health():

    return {"status": "ok", "architecture": "mvc"}





@app.websocket("/ws/{family_id}")

async def websocket_endpoint(websocket: WebSocket, family_id: int, token: str = ""):

    if not token:

        await websocket.close(code=4001)

        return



    try:

        payload = decode_access_token(token)

        token_family = payload.get("family_id")

        role = payload.get("role")

        if token_family != family_id or role not in ("parent", "child"):

            await websocket.close(code=4001)

            return

    except Exception:

        await websocket.close(code=4001)

        return



    await ws_manager.connect(family_id, websocket)

    try:

        while True:

            await websocket.receive_text()

    except WebSocketDisconnect:

        ws_manager.disconnect(family_id, websocket)


