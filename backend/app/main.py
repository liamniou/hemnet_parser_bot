import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.bot import BotPoller
from app.config import get_settings
from app.db import get_db, init_engine
from app.models import Region, User
from app.routers import admin, auth, listings, me, searches
from app.schemas import RegionPublic
from app.services import telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("apscheduler").setLevel(logging.ERROR)
# httpx logs full request URLs at INFO, and Telegram URLs embed the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("hemnet")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.images_dir.mkdir(parents=True, exist_ok=True)
    init_engine(f"sqlite:///{s.db_path}")
    s.ensure_secret_key()

    bot = BotPoller()
    bot.start()
    sched = None
    if s.scheduler_enabled:
        from app.scheduler import build_scheduler

        sched = build_scheduler()
        sched.start()
    yield
    bot.stop()
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="Hemnet Watch", lifespan=lifespan)
for r in (auth.router, me.router, searches.router, listings.router, admin.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def config():
    s = get_settings()
    return {
        "telegram_bot": telegram.bot_username() if s.telegram_enabled else None,
        "email_enabled": s.smtp_enabled,
        "dev_login": s.dev_login,
    }


@app.get("/api/regions", response_model=list[RegionPublic])
def regions(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Region).where(Region.enabled.is_(True)).order_by(Region.name)).all()


class _Media(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


app.mount("/media", _Media(directory=get_settings().images_dir, check_dir=False), name="media")

if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
