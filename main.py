import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from utils.utils import update_feeds_and_posts
from utils.logs import configure_logging, logger
from fastapi import FastAPI

configure_logging()


async def periodic_update():
    while True:
        logger.info("Running periodic feed update")
        await update_feeds_and_posts()
        logger.info("Feed update completed")
        await asyncio.sleep(900)


# Run update_feeds_and_posts at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_update())
    try:
        yield
    finally:
        task.cancel()  # Cancel the periodic task on shutdown


app = FastAPI(lifespan=lifespan)
app.mount("/app", app)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="data", html=True), name="root")
