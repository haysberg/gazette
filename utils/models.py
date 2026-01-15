import asyncio
from datetime import datetime
from time import mktime

import feedparser
from sqlalchemy import Index
from sqlmodel import Field, Relationship, Session, SQLModel

from utils import engine
from utils.logs import logger

# Set a timeout for feedparser requests (30 seconds)
feedparser.SOCKET_TIMEOUT = 30


class Feed(SQLModel, table=True):
	link: str = Field(primary_key=True)
	domain: str
	title: str
	subtitle: str = Field(default='')
	image: str = Field(default='')
	posts: list['Post'] = Relationship(back_populates='feed')

	# Failure tracking
	failure_count: int = Field(default=0)
	last_error: str | None = Field(default=None)
	last_success: datetime | None = Field(default=None)

	@classmethod
	async def init_feed(cls, feed_dict: dict):
		logger.info(f'Initializing feed {feed_dict["link"]}')
		feed = None
		error_msg = None

		try:
			# Parse feed with timeout (non-blocking, retries happen on next 15-min cycle)
			data: dict = await asyncio.to_thread(feedparser.parse, feed_dict['link'])

			# Check if feedparser detected malformed feed
			if data.bozo:
				# Log but don't fail - many feeds have minor issues that feedparser can work around
				logger.warning(
					f'Feed {feed_dict["link"]} has formatting issues but may still be usable: '
					f'{getattr(data.bozo_exception, "getMessage", lambda: str(data.bozo_exception))()}'
				)
				# Only raise if we have no usable data
				if not hasattr(data, 'feed') or not data.entries:
					raise SyntaxError(
						f'Feed {feed_dict["link"]} is too malformed to parse: '
						f'{getattr(data.bozo_exception, "getMessage", lambda: str(data.bozo_exception))()}'
					)

			feed = Feed(
				link=data.feed.link if hasattr(data.feed, 'link') else feed_dict['link'],
				domain=(data.feed.link if hasattr(data.feed, 'link') else feed_dict['link'])
				.split('/')[2]
				.removeprefix('www.'),
				title=data.feed.title
				if hasattr(data.feed, 'title')
				else feed_dict.get('title', 'Unknown'),
				subtitle=data.feed.subtitle if hasattr(data.feed, 'subtitle') else '',
				image=data.feed.image.href
				if hasattr(data.feed, 'image') and hasattr(data.feed.image, 'href')
				else None,
				last_success=datetime.now(),
				failure_count=0,
			)

			# Override with config values if provided
			for key, value in feed_dict.items():
				if hasattr(feed, key):
					setattr(feed, key, value)

			with Session(engine) as session:
				session.merge(feed)
				session.commit()

			logger.info(f'Successfully initialized feed {feed_dict["link"]}')
			return feed

		except (AttributeError, KeyError) as e:
			error_msg = f'Invalid feed structure: {str(e)}'
			logger.error(f'Feed {feed_dict["link"]} does not have a valid structure. {e}')
		except (ConnectionError, ConnectionResetError, TimeoutError) as e:
			error_msg = f'Connection error: {str(e)}'
			logger.error(f"Couldn't connect to {feed_dict['link']}, reason is {e}")
		except SyntaxError as e:
			error_msg = f'Malformed feed: {str(e)}'
			logger.error(f'Feed {feed_dict["link"]} is malformed: {e}')
		except Exception as e:
			error_msg = f'Unexpected error: {str(e)}'
			logger.error(f'Unexpected error initializing feed {feed_dict["link"]}: {e}')

		# Save failed feed with error information
		if error_msg:
			try:
				with Session(engine) as session:
					failed_feed = Feed(
						link=feed_dict['link'],
						domain=feed_dict['link'].split('/')[2].removeprefix('www.'),
						title=feed_dict.get('title', 'Unknown'),
						subtitle=feed_dict.get('subtitle', ''),
						image=feed_dict.get('image', ''),
						failure_count=1,
						last_error=error_msg[:500],  # Limit error message length
					)
					session.merge(failed_feed)
					session.commit()
			except Exception as db_error:
				logger.error(f'Failed to save error state for {feed_dict["link"]}: {db_error}')

		return None

	async def update_posts(self):
		error_msg = None
		posts_added = 0

		try:
			# Parse feed with timeout (non-blocking, retries happen on next 15-min cycle)
			data: dict = await asyncio.to_thread(feedparser.parse, self.link)

			# Check for malformed feed
			if data.bozo:
				logger.warning(
					f'Feed {self.link} has formatting issues: '
					f'{getattr(data.bozo_exception, "getMessage", lambda: str(data.bozo_exception))()}'
				)
				# Only fail if we have no entries at all
				if not data.entries:
					raise SyntaxError(f'Feed {self.link} returned no entries due to parsing errors')

			with Session(engine) as session:
				for entry in data.entries:
					try:
						# Validate required fields exist
						if not hasattr(entry, 'link') or not hasattr(entry, 'title'):
							logger.warning(
								f'Entry from {self.title} missing required fields (link or title), skipping'
							)
							continue

						# Get publication date with fallback chain
						pub_date = None
						if hasattr(entry, 'published_parsed') and entry.published_parsed:
							try:
								pub_date = datetime.fromtimestamp(mktime(entry.published_parsed))
							except (ValueError, OverflowError, OSError) as e:
								logger.warning(
									f'Invalid published_parsed date in {self.title}: {e}'
								)

						if (
							not pub_date
							and hasattr(entry, 'updated_parsed')
							and entry.updated_parsed
						):
							try:
								pub_date = datetime.fromtimestamp(mktime(entry.updated_parsed))
							except (ValueError, OverflowError, OSError) as e:
								logger.warning(f'Invalid updated_parsed date in {self.title}: {e}')

						if not pub_date:
							# Use current time as fallback
							pub_date = datetime.now()
							logger.warning(
								f'Entry from {self.title} has no valid date, using current time'
							)

						# Prepare the Post object
						parsed_entry = Post(
							link=entry.link,
							title=entry.title,
							feed_link=self.link,
							publication_date=pub_date,
						)

						session.merge(parsed_entry)
						posts_added += 1

					except AttributeError as ae:
						logger.error(
							f'An entry from {self.title} does not have a valid structure: {ae}'
						)
						continue
					except Exception as e:
						logger.error(
							f'Unexpected error while processing entry from {self.title}: {e}'
						)
						continue

				try:
					session.commit()

					# Update success tracking
					self.last_success = datetime.now()
					self.failure_count = 0
					self.last_error = None
					session.merge(self)
					session.commit()

					logger.info(f'Successfully updated {posts_added} posts from {self.title}')

				except Exception as commit_exc:
					logger.error(f'Session commit failed for {self.title}: {commit_exc}')
					session.rollback()
					raise

		except (ConnectionError, ConnectionResetError, TimeoutError) as e:
			error_msg = f'Connection error: {str(e)}'
			logger.error(f"Couldn't connect to {self.link}, reason is {e}")
		except SyntaxError as e:
			error_msg = f'Malformed feed: {str(e)}'
			logger.error(f'Feed {self.link} is malformed: {e}')
		except Exception as e:
			error_msg = f'Unexpected error: {str(e)}'
			logger.error(f'Unexpected error in update_posts for {self.link}: {e}')

		# Update failure tracking if there was an error
		if error_msg:
			try:
				with Session(engine) as session:
					# Increment failure count and update error message
					feed = session.get(Feed, self.link)
					if feed:
						feed.failure_count += 1
						feed.last_error = error_msg[:500]  # Limit error message length
						session.merge(feed)
						session.commit()
						logger.warning(f'Feed {self.link} failure count: {feed.failure_count}')
			except Exception as db_error:
				logger.error(f'Failed to update error state for {self.link}: {db_error}')

		return None


class Post(SQLModel, table=True):
	__table_args__ = (Index('idx_post_publication_date', 'publication_date'),)

	link: str = Field(primary_key=True)
	title: str
	feed_link: str = Field(foreign_key='feed.link')
	feed: Feed = Relationship(back_populates='posts')
	publication_date: datetime
