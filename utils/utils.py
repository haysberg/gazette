import asyncio
from datetime import datetime, timedelta
import json
import os
import aiofiles
from sqlmodel import Session, delete, select
from utils.models import Feed, Post
from utils import engine
from utils.logs import logger
from sqlalchemy.orm import selectinload
import tomllib
from datetime import datetime
from utils import STATIC_DIR, TEMPLATES_DIR, HTML_FILE, PLUS_FILE, JSON_FILE
from jinja2 import Environment, FileSystemLoader
import gzip
import brotli
import zstandard as zstd


async def update_all_posts() -> None:
    logger.info("Updating posts")
    with Session(engine) as session:
        feeds = (session.exec(select(Feed))).all()
    tasks = [feed.update_posts() for feed in feeds]
    await asyncio.gather(*tasks)
    logger.info("Finished updating posts.")

    # Delete entries older than a week
    with Session(engine) as session:
        # Delete entries in db older than a week
        logger.debug("Running cleanup of old posts...")
        statement = delete(Post).where(
            Post.publication_date < datetime.now() - timedelta(weeks=1)
        )
        session.exec(statement)
        session.commit()
    await update_served_files()
    await compress_static_files()


async def update_served_files() -> None:
    logger.info("Generating static files...")
    os.makedirs(STATIC_DIR, exist_ok=True)

    posts_last24h: list[Post] = []
    posts_later: list[Post] = []

    # Initialize Jinja2 environment
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

    

    with Session(engine) as session:
        # Get posts from the last 24 hours
        statement = (
            select(Post)
            .options(selectinload(Post.feed))
            .where(Post.publication_date > datetime.now() - timedelta(days=1))
            .order_by(Post.publication_date.desc())
        )
        results = session.exec(statement)
        posts_last24h = results.all()

        # Get posts from later
        statement = (
            select(Post)
            .options(selectinload(Post.feed))
            .where(Post.publication_date < datetime.now() - timedelta(days=1))
            .order_by(Post.publication_date.desc())
        )
        results = session.exec(statement)
        posts_later = results.all()

        # Get all feeds
        feeds = (session.exec(select(Feed).order_by(Feed.title.desc()))).all()
        render_time = datetime.now().strftime("%Hh%M").capitalize()

        # Render Jinja2 template and save as HTML
        try:
            # Render index.html
            template = env.get_template("index.html")
            index_html = template.render(
                posts=posts_last24h,
                feeds=feeds,
                plus=True,
                render_time=render_time,
            )

            # Render plus.html
            plus_html = template.render(
                posts=posts_later,
                feeds=feeds,
                plus=False,
                render_time=render_time,
            )

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

async def compress_static_files() -> None:
    for root, dirs, files in os.walk("static"):
        for file in files:
            file_path = os.path.join(root, file)
            if not file.endswith((".gz", ".br", ".zst")):  # Skip already compressed files
                async with aiofiles.open(file_path, "rb") as f_in:
                    data = await f_in.read()
                gz_path = file_path + ".gz"
                async with aiofiles.open(gz_path, "wb") as f_out:
                    compressed = gzip.compress(data)
                    await f_out.write(compressed)
                # Brotli compression
                try:
                    br_path = file_path + ".br"
                    compressed_br = brotli.compress(data)
                    async with aiofiles.open(br_path, "wb") as f_br:
                        await f_br.write(compressed_br)
                except ImportError:
                    logger.warning("brotli module not installed, skipping Brotli compression for %s", file_path)

                # Zstandard compression
                try:
                    zst_path = file_path + ".zst"
                    cctx = zstd.ZstdCompressor()
                    compressed_zst = cctx.compress(data)
                    async with aiofiles.open(zst_path, "wb") as f_zst:
                        await f_zst.write(compressed_zst)
                except ImportError:
                    logger.warning("zstandard module not installed, skipping Zstandard compression for %s", file_path)

async def init_service() -> None:
    with open("config.toml", "rb") as f:
        content = f.read()
        config_data = tomllib.loads(content.decode("utf-8"))
        logger.debug(f"Found {len(config_data['feeds']['feedlist'])} feeds")

    logger.info("Initializing feeds...")
    tasks = [
        Feed.init_feed(feed_dict) for feed_dict in config_data["feeds"]["feedlist"]
    ]
    await asyncio.gather(*tasks)
