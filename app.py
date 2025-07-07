from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel
from utils.utils import init_service, update_all_posts
from utils.logs import configure_logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils import engine
import subprocess

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    subprocess.Popen(["/bin/static-web-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await init_service()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        update_all_posts,
        "interval",
        minutes=15,
        max_instances=1,
        next_run_time=datetime.now(),
    )
    scheduler.start()

    yield


app = FastAPI(lifespan=lifespan, ocs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
app.mount("/", StaticFiles(directory="static", html=True), name="root")
