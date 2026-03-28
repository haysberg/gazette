import asyncio
from datetime import datetime
from time import mktime

import feedparser
from sqlalchemy import Index
from sqlmodel import Field, Relationship, Session, SQLModel

from utils import engine
from utils.logs import logger

FEED_TIMEOUT = 30


class Feed(SQLModel, table=True):
	link: str = Field(primary_key=True)
	domain: str
	title: str
	subtitle: str = Field(default='')
	image: str = Field(default='')
	posts: list['Post'] = Relationship(back_populates='feed')

	# Throttle: max number of posts to keep from this feed
	max_posts: int | None = Field(default=None)

	# Conditional fetching (ETag / Last-Modified)
	etag: str | None = Field(default=None)
	modified: str | None = Field(default=None)

	# Failure tracking
	failure_count: int = Field(default=0)
	last_error: str | None = Field(default=None)
	last_success: datetime | None = Field(default=None)

	@classmethod
	async def init_feed(cls, feed_dict: dict):
		logger.info('Initializing feed', feed=feed_dict['link'])
		error_msg = None

		try:
			data: dict = await asyncio.wait_for(
				asyncio.to_thread(feedparser.parse, feed_dict['link']),
				timeout=FEED_TIMEOUT,
			)

			if data.bozo:
				bozo_msg = getattr(
					data.bozo_exception, 'getMessage', lambda: str(data.bozo_exception)
				)()
				logger.warning('Feed has formatting issues', feed=feed_dict['link'], issue=bozo_msg)
				if not hasattr(data, 'feed') or not data.entries:
					raise SyntaxError(f'Feed too malformed to parse: {bozo_msg}')

			feed = Feed(
				link=getattr(data.feed, 'link', feed_dict['link']),
				domain=getattr(data.feed, 'link', feed_dict['link'])
				.split('/')[2]
				.removeprefix('www.'),
				title=getattr(data.feed, 'title', feed_dict.get('title', 'Unknown')),
				subtitle=getattr(data.feed, 'subtitle', ''),
				image=getattr(getattr(data.feed, 'image', None), 'href', None),
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

			logger.info('Successfully initialized feed', feed=feed_dict['link'])
			return feed

		except (AttributeError, KeyError) as e:
			error_msg = f'Invalid feed structure: {e}'
			logger.error('Invalid feed structure', feed=feed_dict['link'], error=str(e))
		except (ConnectionError, ConnectionResetError, TimeoutError, asyncio.TimeoutError) as e:
			error_msg = f'Connection error: {e}'
			logger.error('Connection failed', feed=feed_dict['link'], error=str(e))
		except SyntaxError as e:
			error_msg = f'Malformed feed: {e}'
			logger.error('Malformed feed', feed=feed_dict['link'], error=str(e))
		except Exception as e:
			error_msg = f'Unexpected error: {e}'
			logger.error('Unexpected error initializing feed', feed=feed_dict['link'], error=str(e))

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
						last_error=error_msg[:500],
					)
					session.merge(failed_feed)
					session.commit()
			except Exception as db_error:
				logger.error(
					'Failed to save error state', feed=feed_dict['link'], error=str(db_error)
				)

		return None

	async def update_posts(self):
		error_msg = None
		posts_added = 0

		try:
			data: dict = await asyncio.wait_for(
				asyncio.to_thread(
					feedparser.parse, self.link, etag=self.etag, modified=self.modified
				),
				timeout=FEED_TIMEOUT,
			)

			# Handle 304 Not Modified
			if hasattr(data, 'status') and data.status == 304:
				logger.debug('Feed not modified, skipping', feed=self.title)
				return None

			if data.bozo:
				bozo_msg = getattr(
					data.bozo_exception, 'getMessage', lambda: str(data.bozo_exception)
				)()
				logger.warning('Feed has formatting issues', feed=self.link, issue=bozo_msg)
				if not data.entries:
					raise SyntaxError(f'Feed returned no entries due to parsing errors')

			with Session(engine) as session:
				for entry in data.entries:
					try:
						if not hasattr(entry, 'link') or not hasattr(entry, 'title'):
							logger.warning(
								'Entry missing required fields, skipping', feed=self.title
							)
							continue

						# Get publication date with fallback chain
						pub_date = None
						if hasattr(entry, 'published_parsed') and entry.published_parsed:
							try:
								pub_date = datetime.fromtimestamp(mktime(entry.published_parsed))
							except (ValueError, OverflowError, OSError) as e:
								logger.warning(
									'Invalid published_parsed date', feed=self.title, error=str(e)
								)

						if (
							not pub_date
							and hasattr(entry, 'updated_parsed')
							and entry.updated_parsed
						):
							try:
								pub_date = datetime.fromtimestamp(mktime(entry.updated_parsed))
							except (ValueError, OverflowError, OSError) as e:
								logger.warning(
									'Invalid updated_parsed date', feed=self.title, error=str(e)
								)

						if not pub_date:
							pub_date = datetime.now()
							logger.warning(
								'Entry has no valid date, using current time', feed=self.title
							)

						parsed_entry = Post(
							link=entry.link,
							title=entry.title,
							feed_link=self.link,
							publication_date=pub_date,
						)

						session.merge(parsed_entry)
						posts_added += 1

					except AttributeError as ae:
						logger.error('Invalid entry structure', feed=self.title, error=str(ae))
						continue
					except Exception as e:
						logger.error('Error processing entry', feed=self.title, error=str(e))
						continue

				# Single transaction: commit posts + update feed metadata
				feed = session.get(Feed, self.link)
				if feed:
					feed.last_success = datetime.now()
					feed.failure_count = 0
					feed.last_error = None
					feed.etag = getattr(data, 'etag', None)
					feed.modified = getattr(data, 'modified', None)

				try:
					session.commit()
					logger.info('Updated posts', feed=self.title, count=posts_added)
				except Exception as commit_exc:
					logger.error('Session commit failed', feed=self.title, error=str(commit_exc))
					session.rollback()
					raise

		except (ConnectionError, ConnectionResetError, TimeoutError, asyncio.TimeoutError) as e:
			error_msg = f'Connection error: {e}'
			logger.error('Connection failed', feed=self.link, error=str(e))
		except SyntaxError as e:
			error_msg = f'Malformed feed: {e}'
			logger.error('Malformed feed', feed=self.link, error=str(e))
		except Exception as e:
			error_msg = f'Unexpected error: {e}'
			logger.error('Unexpected error in update_posts', feed=self.link, error=str(e))

		if error_msg:
			try:
				with Session(engine) as session:
					feed = session.get(Feed, self.link)
					if feed:
						feed.failure_count += 1
						feed.last_error = error_msg[:500]
						session.commit()
						logger.warning(
							'Feed failure count incremented',
							feed=self.link,
							count=feed.failure_count,
						)
			except Exception as db_error:
				logger.error('Failed to update error state', feed=self.link, error=str(db_error))

		return None


class Post(SQLModel, table=True):
	__table_args__ = (Index('idx_post_publication_date', 'publication_date'),)

	link: str = Field(primary_key=True)
	title: str
	feed_link: str = Field(foreign_key='feed.link')
	feed: Feed = Relationship(back_populates='posts')
	publication_date: datetime
