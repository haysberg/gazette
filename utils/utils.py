import asyncio
from datetime import datetime, timedelta
import json
import os
import aiofiles
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession
from utils.models import Feed, Post
from utils import engine
from utils.logs import logger
from sqlalchemy.orm import selectinload
from fastapi.templating import Jinja2Templates
import tomllib
from datetime import datetime
from utils import STATIC_DIR, TEMPLATES_DIR, HTML_FILE, PLUS_FILE, JSON_FILE




async def update_all_posts() -> None:
    logger.info("Updating posts")
    async with AsyncSession(engine) as session:
        feeds = (await session.exec(select(Feed))).all()
    tasks = [feed.update_posts() for feed in feeds]
    await asyncio.gather(*tasks)
    logger.info("Finished updating posts.")

    # Delete entries older than a week
    async with AsyncSession(engine) as session:
        # Delete entries in db older than a week
        logger.debug("Running cleanup of old posts...")
        statement = delete(Post).where(
            Post.publication_date < datetime.now() - timedelta(weeks=1)
        )
        await session.exec(statement)
        await session.commit()
    await update_served_files()

async def update_served_files() -> None:
    logger.info("Generating static files...")
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    os.makedirs(STATIC_DIR, exist_ok=True)

    posts_last24h: list[Post] = []
    posts_later: list[Post] = []

    async with AsyncSession(engine) as session:
        # Get posts from the last 24 hours
        statement = (
            select(Post)
            .options(selectinload(Post.feed))
            .where(Post.publication_date > datetime.now() - timedelta(days=1))
            .order_by(Post.publication_date.desc())
        )
        results = await session.exec(statement)
        posts_last24h = results.all()

        # Get posts from later
        statement = (
            select(Post)
            .options(selectinload(Post.feed))
            .where(Post.publication_date < datetime.now() - timedelta(days=1))
            .order_by(Post.publication_date.desc())
        )
        results = await session.exec(statement)
        posts_later = results.all()

        # Get all feeds
        feeds = (await session.exec(select(Feed).order_by(Feed.title.desc()))).all()
        render_time = datetime.now().strftime("%Hh%M").capitalize()

        # Render Jinja2 template and save as HTML
        try:
            # Render index.html
            index_html = templates.TemplateResponse(
                name="index.html",
                context={
                    "request": None,  # No request object needed for static rendering
                    "posts": posts_last24h,
                    "feeds": feeds,
                    "plus": True,
                    "render_time": render_time,
                },
            ).body.decode("utf-8")

            # Render plus.html
            plus_html = templates.TemplateResponse(
                name="index.html",
                context={
                    "request": None,  # No request object needed for static rendering
                    "posts": posts_later,
                    "feeds": feeds,
                    "plus": False,
                    "render_time": render_time,
                },
            ).body.decode("utf-8")

            # Generate JSON and save as a file
            json_data = {
                "posts_last24h": [post.model_dump() for post in posts_last24h],
                "posts_later": [post.model_dump() for post in posts_later],
                "feeds": [feed.model_dump() for feed in feeds],
            }
            logger.debug("Pages rendered successfully !")
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return

    try:
        async with aiofiles.open(HTML_FILE, "w") as f:
            await f.write(index_html)
        logger.debug(f"HTML file saved to {HTML_FILE}")

        async with aiofiles.open(PLUS_FILE, "w") as f:
            await f.write(plus_html)
        logger.debug(f"PLUS file saved to {PLUS_FILE}")

        async with aiofiles.open(JSON_FILE, "w") as f:
            await f.write(json.dumps(json_data, sort_keys=True, default=str))
        logger.debug(f"JSON file saved to {JSON_FILE}")

    except Exception as e:
        logger.error(f"Failed to save file: {e}")

    logger.debug("Static files generation ended.")

async def init_service() -> None:
    async with aiofiles.open("config.toml", "rb") as f:
        content = await f.read()
        config_data = tomllib.loads(content.decode("utf-8"))
        logger.debug(f"Found {len(config_data['feeds']['feedlist'])} feeds")

    logger.info("Initializing feeds...")

    semaphore = asyncio.Semaphore(10)

    tasks = [Feed.init_feed(feed_dict) for feed_dict in config_data["feeds"]["feedlist"]]
    await asyncio.gather(*tasks)