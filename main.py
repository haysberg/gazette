import locale
from fastapi import FastAPI
from contextlib import asynccontextmanager

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from utils.utils import STATIC_DIR, update_feeds_and_posts
from utils.logs import configure_logging, logger
from fastapi import FastAPI
import asyncio

configure_logging()


async def periodic_update():
    while True:
        logger.info("Running periodic feed update")
        await update_feeds_and_posts()
        logger.info("Feed update completed")
        await asyncio.sleep(60)


# Run update_feeds_and_posts at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_update())
    try:
        yield
    finally:
        task.cancel()  # Cancel the periodic task on shutdown


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index(json: bool = False):
    if json:
        return FileResponse(STATIC_DIR + "/index.json")
    return FileResponse(STATIC_DIR + "/index.html")
