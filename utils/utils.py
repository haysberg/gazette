import asyncio
from datetime import datetime, timedelta
import json
import os
from time import mktime
import feedparser
from sqlmodel import Session, delete, select
from models.models import Feed, Post
from utils.db import engine
from utils.logs import logger
from sqlalchemy.orm import selectinload
from fastapi.templating import Jinja2Templates
import tomllib
from datetime import datetime
from PIL import Image
from io import BytesIO
import httpx

# Paths for static files
STATIC_DIR = "tmp"
os.makedirs(STATIC_DIR, exist_ok=True)
HTML_FILE = os.path.join(STATIC_DIR, "index.html")
PLUS_FILE = os.path.join(STATIC_DIR, "plus.html")
JSON_FILE = os.path.join(STATIC_DIR, "index.json")
templates = Jinja2Templates(directory="templates")


async def update_feeds_and_posts() -> None:
    with open("config.toml", "rb") as f:
        config_data = tomllib.load(f)
    logger.info("Running recurrent feed update...")
    # Add debug logging to verify tasks creation
    logger.debug(f"Creating tasks for {len(config_data['feeds']['feedlist'])} feeds")

    # Run parse_feed concurrently for all feed URLs
    tasks = [parse_feed(feed_dict) for feed_dict in config_data["feeds"]["feedlist"]]
    logger.debug(f"Created {len(tasks)} tasks")

    results = await asyncio.gather(*tasks)
    logger.info(f"Finished parsing {len([r for r in results if r is not None])} feeds.")

    # Delete entries older than a week
    with Session(engine) as session:
        # Delete entries in db older than a week
        logger.info("Running cleanup of old posts...")
        statement = delete(Post).where(
            Post.publication_date < datetime.now() - timedelta(weeks=1)
        )
        session.exec(statement)
        session.commit()

    await update_served_files()


async def update_served_files() -> None:
    logger.info("Generating static files...")

    os.makedirs(STATIC_DIR, exist_ok=True)

    posts_last24h: list[Post] = []
    posts_24_48h: list[Post] = []
    posts_later: list[Post] = []

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
        statement = select(Feed)
        results = session.exec(statement)
        feeds = results.all()
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
                name="plus.html",
                context={
                    "request": None,  # No request object needed for static rendering
                    "posts": posts_later,
                    "feeds": feeds,
                    "render_time": render_time,
                },
            ).body.decode("utf-8")
            logger.info("HTML pages rendered successfully !")
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return

    try:
        with open(HTML_FILE, "w") as f:
            f.write(index_html)
        logger.info(f"HTML file saved to {HTML_FILE}")
    except Exception as e:
        logger.error(f"Failed to save HTML file: {e}")

    try:
        with open(PLUS_FILE, "w") as f:
            f.write(plus_html)
        logger.info(f"HTML file saved to {PLUS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save HTML file: {e}")

    # Generate JSON and save as a file
    json_data = {
        "posts_last24h": [post.model_dump() for post in posts_last24h],
        "posts_later": [post.model_dump() for post in posts_later],
        "feeds": [feed.model_dump() for feed in feeds],
    }
    try:
        with open(JSON_FILE, "w") as f:
            json.dump(json_data, f, indent=4, default=str)
        logger.info(f"JSON file saved to {JSON_FILE}")
    except Exception as e:
        logger.error(f"Failed to save JSON file: {e}")

    # Download images to STATIC_DIR/favicons and convert them to webp, 64x64
    for feed in feeds:
        if feed.image:
            try:
                # Skip if image already present in folder
                if os.path.exists(
                    os.path.join(STATIC_DIR, "favicons", f"{feed.domain}.webp")
                ):
                    logger.info(
                        f"Image for {feed.domain} already exists, skipping download."
                    )
                    continue
                image_path = os.path.join(STATIC_DIR, "favicons", f"{feed.domain}.webp")
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                with httpx.Client(timeout=10) as client:
                    response = client.get(feed.image)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content)).convert("RGBA")
                img = img.resize((32, 32), Image.LANCZOS)
                img.save(image_path, "WEBP")
                logger.info(f"Image for {feed.domain} saved to {image_path}")
            except Exception as e:
                logger.error(f"Failed to save image for {feed.domain}: {e}")

    logger.info("Static files generation ended.")


async def parse_feed(feed_dict: dict) -> None:
    logger.debug(f"Parsing feed {feed_dict}")
    try:
        data: dict = feedparser.parse(feed_dict["link"])
    except ConnectionResetError as cre:
        logger.error(f"Couldn't connect to {feed_dict['link']}, reason is {cre}")
        return None

    if data.bozo:
        logger.error(
            f"Feed {feed_dict['link']} is not valid. Gave the following error: {data.bozo_exception}"
        )
        return None
    try:
        parsed_feed = Feed(
            link=data.feed.link,
            domain=data.feed.link.split("/")[2].removeprefix("www."),
            title=data.feed.title,
            subtitle=data.feed.subtitle,
            image=data.feed.image.href if hasattr(data.feed, "image") else None,
        )

        # Merge feed_dict into parsed_feed, overriding only if the value is set in feed_dict
        for key, value in feed_dict.items():
            if value:  # Only override if the value is set (not None or empty)
                setattr(parsed_feed, key, value)

    except (AttributeError, KeyError) as e:
        logger.error(f"Feed {feed_dict['link']} does not have a valid structure. {e}")
        logger.error(data.feed)
        return None

    with Session(engine) as session:
        parsed_feed.image = parsed_feed.image.replace("http://", "https://")
        parsed_feed = session.merge(parsed_feed)
        logger.debug(f"Feed {parsed_feed.link} parsed and saved successfully.")

        for entry in data.entries:
            try:
                if "published_parsed" not in entry:
                    entry.published_parsed = (
                        entry.updated_parsed
                        if hasattr(entry, "updated_parsed")
                        else None
                    )

                if not entry.published_parsed:
                    logger.warning(
                        f"Entry {entry.get('title', 'No title')} has no valid date, skipping"
                    )
                    continue

                # Prepare the Post object
                parsed_entry = {
                    "link": entry.link,
                    "title": entry.title,
                    "author": entry.author if hasattr(entry, "author") else None,
                    "tags": entry.tags if hasattr(entry, "tags") else [],
                    "feed_link": parsed_feed.link,  # Use feed_id instead of the full object
                    "publication_date": datetime.fromtimestamp(
                        mktime(entry.published_parsed)
                    ),
                }

                # Check if the entry already exists
                existing_post = session.exec(
                    select(Post).where(Post.link == entry.link)
                ).first()
                if existing_post:
                    # Update the existing entry
                    existing_post.title = parsed_entry["title"]
                    existing_post.author = parsed_entry["author"]
                    existing_post.tags = parsed_entry["tags"]
                    existing_post.feed_link = parsed_entry["feed_link"]
                    existing_post.publication_date = parsed_entry["publication_date"]
                else:
                    # Insert a new entry
                    session.add(Post(**parsed_entry))

            except AttributeError as ae:
                logger.error(
                    f"An entry from {parsed_feed.title} does not have a valid structure: {ae}"
                )
                continue

        session.commit()
        return parsed_feed
