from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime


class Feed(SQLModel, table=True):
    link: str = Field(primary_key=True)
    domain: str
    title: str
    subtitle: str = Field(default="")
    image: str = Field(default="")
    posts: list["Post"] = Relationship(back_populates="feed")


class Post(SQLModel, table=True):
    link: str = Field(primary_key=True)
    title: str
    feed_link: str = Field(foreign_key="feed.link")
    feed: Feed = Relationship(back_populates="posts")
    score: int = Field(default=0)
    publication_date: datetime
