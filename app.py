import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from utils.utils import update_feeds_and_posts
from utils.logs import configure_logging, logger
import shutil

configure_logging()


async def periodic_update():
    while True:
        logger.info("Running periodic feed update")
        asyncio.create_task(update_feeds_and_posts())
        logger.info("Feed update completed")
        await asyncio.sleep(900)


# Run update_feeds_and_posts at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # If tmp folder does not exist, create it
    os.makedirs("tmp", exist_ok=True)
    # Copy everything from data folder to tmp folder
    if os.path.exists("data"):
        for item in os.listdir("data"):
            s = os.path.join("data", item)
            d = os.path.join("tmp", item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
    task = asyncio.create_task(periodic_update())
    try:
        yield
    finally:
        task.cancel()  # Cancel the periodic task on shutdown


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
app.mount("/app", app)
app.mount("/", StaticFiles(directory="static", html=True), name="root")
