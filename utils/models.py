import asyncio
from datetime import datetime
from io import BytesIO
import os
from time import mktime

import feedparser
import cairosvg
from utils.logs import logger
import httpx
from sqlmodel import Field, Relationship, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from PIL import Image
from utils import engine

class Feed(SQLModel, table=True):
    link: str = Field(primary_key=True)
    domain: str
    title: str
    subtitle: str = Field(default="")
    image: str = Field(default="")
    posts: list["Post"] = Relationship(back_populates="feed")

    async def download_image(self):
        try:
            image_path = os.path.join("static", "favicons", f"{self.domain}.webp")
            os.makedirs(os.path.dirname(image_path), exist_ok=True)

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.image)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as http_err:
                    logger.error(f"HTTP error while downloading image for {self.domain}: {http_err}")
                    return
            
            img_data = BytesIO(response.content)
            if self.image.endswith('.svg'):
                png_data = BytesIO()
                cairosvg.svg2png(bytestring=img_data.getvalue(), write_to=png_data)
                img_data = png_data

            Image.open(img_data).resize((32, 32), Image.LANCZOS).save(image_path, 'WEBP')
            logger.debug(f"Image for {self.domain} saved to {image_path}")
        except Exception as e:
            logger.error(f"Failed to save image for {self.domain}: {e}")

    @classmethod
    async def init_feed(cls, feed_dict: dict):
        logger.debug(f"Initializing feed {feed_dict['link']}")
        try:
            data: dict = await asyncio.to_thread(feedparser.parse, feed_dict["link"])

            if data.bozo:
                raise SyntaxError(f"Issue when updating feed {feed_dict['link']}: {data.bozo_exception.getMessage()}")

            feed = Feed(
                link=data.feed.link,
                domain=data.feed.link.split("/")[2].removeprefix("www."),
                title=data.feed.title,
                subtitle=data.feed.subtitle if hasattr(data.feed, "subtitle") else "",
                image=data.feed.image.href if hasattr(data.feed, "image") else None,
            )

            for key, value in feed_dict.items():
                setattr(feed, key, value)
            async with AsyncSession(engine) as session:
                await session.merge(feed)
                await session.commit()
            asyncio.create_task(feed.download_image())
            return feed

        except (AttributeError, KeyError) as e:
            logger.error(
                f"Feed {feed_dict['link']} does not have a valid structure. {e}"
            )
            logger.error(data.feed)
            return None
        except ConnectionResetError as cre:
            logger.error(f"Couldn't connect to {feed_dict['link']}, reason is {cre}")
            return None

    async def update_posts(self):
        try:
            data: dict = feedparser.parse(self.link)
            async with AsyncSession(engine) as session:
                for entry in data.entries:
                    try:
                        # Prepare the Post object
                        parsed_entry = Post(
                            link=entry.link,
                            title=entry.title,
                            feed_link=self.link,
                            publication_date=datetime.fromtimestamp(
                                mktime(entry.published_parsed if hasattr(entry, "published_parsed") else entry.updated_parsed)
                            ),
                        )

                        await session.merge(parsed_entry)

                    except AttributeError as ae:
                        logger.error(
                            f"An entry from {self.title} does not have a valid structure: {ae}"
                        )
                        continue
                    except Exception as e:
                        logger.error(
                            f"Unexpected error while processing entry from {self.title}: {e}"
                        )
                        continue
                try:
                    await session.commit()
                except Exception as commit_exc:
                    logger.error(f"Session commit failed: {commit_exc}")
                    await session.rollback()
        except ConnectionResetError as cre:
            logger.error(f"Couldn't connect to {self.link}, reason is {cre}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in update_posts: {e}")
            return None

class Post(SQLModel, table=True):
    link: str = Field(primary_key=True)
    title: str
    feed_link: str = Field(foreign_key="feed.link")
    feed: Feed = Relationship(back_populates="posts")
    publication_date: datetime