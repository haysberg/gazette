from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from utils.utils import STATIC_DIR, update_feeds_and_posts
from utils.logs import configure_logging, logger
from fastapi import FastAPI
import uvicorn
import asyncio

configure_logging()


async def periodic_update():
    while True:
        logger.info("Running periodic feed update")
        await update_feeds_and_posts()
        logger.info("Feed update completed")
        await asyncio.sleep(600)  # Wait for 10 minutes (600 seconds)


# Run update_feeds_and_posts at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Running startup tasks")
    await update_feeds_and_posts()
    task = asyncio.create_task(periodic_update())  # Start periodic updates
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


if __name__ == "__main__":
    configure_logging()
    uvicorn.run(
        "app:app",  # Replace with your app's entry point
        host="0.0.0.0",
        port=8000,
        log_config=None,  # Disable Uvicorn's default logging
        access_log=False,  # Disable Uvicorn's access logs
    )
