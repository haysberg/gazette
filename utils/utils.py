import asyncio
from datetime import datetime, timedelta
import os
from time import mktime
from fastapi.templating import Jinja2Templates
import feedparser
from sqlmodel import Session, delete, select
from utils.models import Feed, Post
from utils import engine
from utils.logs import logger
from sqlalchemy.orm import selectinload
import tomllib
from datetime import datetime

FEEDLIST: list[Feed] = list()
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
HTML_FILE = os.path.join(STATIC_DIR, "index.html")
PLUS_FILE = os.path.join(STATIC_DIR, "plus.html")
JSON_FILE = os.path.join(STATIC_DIR, "index.json")
TEMPLATES = Jinja2Templates(directory="templates")


# Updates data for a single source given its URL.
def update_source_data(feed_dict: dict):
    feed = Feed.from_dict(feed_dict)

    with Session(engine) as session:
        session.merge(feed)
        session.commit()
        logger.debug(f"Feed {feed.link} parsed and saved successfully.")
    if feed is not None:
        FEEDLIST.append(feed)


def update_sources() -> None:
    logger.info("Updating sources...")
    with open("config.toml", "rb") as f:
        config_bytes = f.read()
    config_data = tomllib.loads(config_bytes.decode("utf-8"))
    # Add debug logging to verify tasks creation
    logger.debug(f"Creating tasks for {len(FEEDLIST)} feeds")

    # Run parse_feed concurrently for all feed URLs
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        tasks = [
            executor.submit(update_source_data, feed_dict)
            for feed_dict in config_data["feeds"]["feedlist"]
        ]
        concurrent.futures.wait(tasks)
    logger.debug(f"Created {len(tasks)} tasks")
    logger.info(f"Finished parsing feeds.")


def update_posts() -> None:
    logger.info("Running recurrent feed update...")

    tasks = [parse_feed(feed) for feed in FEEDLIST]
    logger.debug(f"Created {len(tasks)} tasks")

    asyncio.gather(*tasks)

    # Delete entries older than a week
    with Session(engine) as session:
        # Delete entries in db older than a week
        logger.info("Running cleanup of old posts...")
        statement = delete(Post).where(
            Post.publication_date < datetime.now() - timedelta(weeks=1)
        )
        session.exec(statement)
        session.commit()


def parse_feed(feed: Feed) -> None:
    data: dict = feedparser.parse(feed.link)
    for entry in data.entries:
        try:
            if "published_parsed" not in entry:
                entry.published_parsed = (
                    entry.updated_parsed if hasattr(entry, "updated_parsed") else None
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
                "author": getattr(entry, "author", None),
                "tags": getattr(entry, "tags", []),
                "feed_link": feed.link,
                "publication_date": datetime.fromtimestamp(
                    mktime(entry.published_parsed)
                ),
            }

            with Session(engine) as session:
                # Check if the entry already exists
                query = session.execute(
                    select(Post).where(Post.link == entry.link)
                )
                existing_post = query.first()
                if existing_post:
                    for key, value in parsed_entry.items():
                        setattr(existing_post, key, value)
                else:
                    session.add(Post(**parsed_entry))
                session.commit()

        except AttributeError as ae:
            logger.error(
                f"An entry from {feed.title} does not have a valid structure: {ae}"
            )
            continue


def update_served_files() -> None:
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
            index_html = TEMPLATES.TemplateResponse(
                    name="index.html",
                    context={
                        "request": None,
                        "posts": posts_last24h,
                        "feeds": feeds,
                        "plus": True,
                        "render_time": render_time,
                    },
                ).body.decode("utf-8")
            plus_html = TEMPLATES.TemplateResponse(
                    name="index.html",
                    context={
                        "request": None,
                        "posts": posts_later,
                        "feeds": feeds,
                        "plus": False,
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

    logger.info("Static files generation ended.")
