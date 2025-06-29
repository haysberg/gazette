import time
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel
from utils.utils import update_posts, update_served_files, update_sources
from utils.logs import configure_logging, logger
from fastapi.concurrency import run_in_threadpool
from utils import engine
from utils.models import Post, Feed


configure_logging()
SQLModel.metadata.create_all(engine)

def periodic():
    update_sources()
    while True:
        update_posts()
        update_served_files()
        time.sleep(3600)  # every hour


# Run update_feeds_and_posts at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(periodic)
    yield


app = FastAPI(lifespan=lifespan, ocs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
app.mount("/", StaticFiles(directory="static", html=True), name="root")
