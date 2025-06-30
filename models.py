from io import BytesIO
import os
from typing import List
import feedparser
import httpx
from sqlmodel import JSON, Column, Field, Relationship, SQLModel
from datetime import datetime
from utils.logs import logger
from PIL import Image
from fastapi.concurrency import run_in_threadpool


class Feed(SQLModel, table=True):
    link: str = Field(primary_key=True)
    domain: str
    title: str
    subtitle: str = Field(default="")
    image: str = Field(default="")
    posts: list["Post"] = Relationship(back_populates="feed")

    @classmethod
    def from_dict(cls, feed_dict: dict):
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
            feed = cls(
                link=data.feed.link,
                domain=data.feed.link.split("/")[2].removeprefix("www."),
                title=data.feed.title,
                subtitle=data.feed.subtitle if hasattr(data.feed, "subtitle") else "",
                image=data.feed.image.href if hasattr(data.feed, "image") else None,
            )

            # Merge feed_dict into parsed_feed, overriding only if the value is set in feed_dict
            for key, value in feed_dict.items():
                if value:  # Only override if the value is set (not None or empty)
                    setattr(feed, key, value)

        except (AttributeError, KeyError) as e:
            logger.error(
                f"Feed {feed_dict['link']} does not have a valid structure. {e}"
            )
            logger.error(data.feed)
            return None
        if feed.image:
            feed.download_image
        return feed

    def download_image(self):
        try:
            image_path = os.path.join("static", "favicons", f"{self.domain}.webp")
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            if os.path.exists(image_path):
                logger.info(
                    f"Image for {self.domain} already exists, skipping download."
                )
                return

            with httpx.Client(timeout=10) as client:
                response = client.get(self.image)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert("RGBA")
            img = img.resize((32, 32), Image.LANCZOS)
            img.save(image_path, "WEBP")
            logger.info(f"Image for {self.domain} saved to {image_path}")
        except Exception as e:
            logger.error(f"Failed to save image for {self.domain}: {e}")


class Post(SQLModel, table=True):
    link: str = Field(primary_key=True)
    title: str
    feed_link: str = Field(foreign_key="feed.link")
    feed: Feed = Relationship(back_populates="posts")
    score: int = Field(default=0)
    author: str = Field(nullable=True)
    tags: List[dict] = Field(default=[], sa_column=Column(JSON))
    publication_date: datetime
