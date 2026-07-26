import asyncio
from datetime import datetime
from time import mktime

import feedparser
import httpx
from sqlalchemy import Index
from sqlmodel import Field, Relationship, Session, SQLModel

from utils import engine
from utils.logs import logger

FEED_TIMEOUT = 30
FEED_CONNECT_TIMEOUT = 10

# Feeds are fetched through a shared client so a handful of slow origins cannot
# saturate a single-vCPU box. `feedparser.parse` used to do its own blocking
# urllib fetch inside a thread, where a hung origin pinned a thread-pool worker
# forever: `asyncio.wait_for` cancels the await, not the thread.
MAX_CONCURRENT_FETCHES = 10

USER_AGENT = 'Gazette/1.0 (+https://insoumis.news/)'

_fetch_semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
_client: httpx.AsyncClient | None = None


class FeedParsingError(Exception):
	"""Raised when a feed is too malformed to parse."""


class FeedNotModified(Exception):
	"""Raised when the origin answers 304 to a conditional request."""


def _get_client() -> httpx.AsyncClient:
	global _client
	if _client is None:
		_client = httpx.AsyncClient(
			timeout=httpx.Timeout(FEED_TIMEOUT, connect=FEED_CONNECT_TIMEOUT),
			follow_redirects=True,
			headers={'User-Agent': USER_AGENT},
			limits=httpx.Limits(max_connections=MAX_CONCURRENT_FETCHES),
		)
	return _client


async def close_client() -> None:
	"""Close the shared HTTP client, if one was ever opened."""
	global _client
	if _client is not None:
		await _client.aclose()
		_client = None


async def fetch_feed(
	url: str, etag: str | None = None, modified: str | None = None
) -> httpx.Response:
	"""Fetch a feed conditionally. Raises FeedNotModified when unchanged."""
	headers = {}
	if etag:
		headers['If-None-Match'] = etag
	if modified:
		headers['If-Modified-Since'] = modified

	async with _fetch_semaphore:
		response = await _get_client().get(url, headers=headers)

	if response.status_code == 304:
		raise FeedNotModified
	response.raise_for_status()
	return response


def _parse_response(response: httpx.Response) -> dict:
	"""Parse already-fetched bytes.

	`content-location` is required: without it feedparser has no base URL, so
	feeds that publish relative entry links leave them unresolved and every
	article link on the page breaks. Content-Type is deliberately not forwarded —
	origins that mislabel feeds as text/html parse fine when feedparser sniffs
	the body itself.
	"""
	return feedparser.parse(
		response.content,
		response_headers={'content-location': str(response.url)},
	)


def _bozo_message(data: dict) -> str:
	return getattr(data.bozo_exception, 'getMessage', lambda: str(data.bozo_exception))()


class Feed(SQLModel, table=True):
	link: str = Field(primary_key=True)
	domain: str
	title: str
	subtitle: str = Field(default='')
	image: str = Field(default='')
	posts: list['Post'] = Relationship(back_populates='feed')

	# Throttle: max number of posts to keep from this feed
	max_posts: int | None = Field(default=None)

	# Only keep free/public articles (filters on accessPermission tag)
	free_only: bool = Field(default=False)

	# Conditional fetching (ETag / Last-Modified)
	etag: str | None = Field(default=None)
	modified: str | None = Field(default=None)

	# Failure tracking
	failure_count: int = Field(default=0)
	last_error: str | None = Field(default=None)
	last_success: datetime | None = Field(default=None)

	@classmethod
	async def init_feed(cls, feed_dict: dict):
		"""Register a feed and store the entries from the very same response.

		The initial fetch used to be thrown away after reading title/subtitle/image,
		and the scheduler then re-fetched all 49 feeds immediately — two full passes
		over the network on every start. Storing the entries here means one pass.
		"""
		logger.info('Initializing feed', feed=feed_dict['link'])
		error_msg = None

		try:
			response = await fetch_feed(feed_dict['link'])
			data: dict = await asyncio.to_thread(_parse_response, response)

			if data.bozo:
				bozo_msg = _bozo_message(data)
				logger.warning('Feed has formatting issues', feed=feed_dict['link'], issue=bozo_msg)
				if not hasattr(data, 'feed') or not data.entries:
					raise FeedParsingError(f'Feed too malformed to parse: {bozo_msg}')

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
				etag=response.headers.get('etag'),
				modified=response.headers.get('last-modified'),
			)

			# Override with config values if provided
			for key, value in feed_dict.items():
				if hasattr(feed, key):
					setattr(feed, key, value)

			with Session(engine) as session:
				# merge() returns the persistent instance; the feed row has to exist
				# before its posts reference it.
				merged = session.merge(feed)
				session.flush()
				posts_added = merged._store_entries(data, session)
				session.commit()

			logger.info('Successfully initialized feed', feed=feed_dict['link'], posts=posts_added)
			return feed

		except (AttributeError, KeyError) as e:
			error_msg = f'Invalid feed structure: {e}'
			logger.error('Invalid feed structure', feed=feed_dict['link'], error=str(e))
		except httpx.HTTPError as e:
			error_msg = f'Connection error: {e}'
			logger.error('Connection failed', feed=feed_dict['link'], error=str(e))
		except FeedParsingError as e:
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

	def _store_entries(self, data: dict, session: Session) -> int:
		"""Merge a parsed feed's entries into `session`. Returns how many were stored."""
		posts_added = 0

		for entry in data.entries:
			try:
				if not hasattr(entry, 'link') or not hasattr(entry, 'title'):
					logger.warning('Entry missing required fields, skipping', feed=self.title)
					continue

				if self.free_only and entry.get('accesspermission', 'free') != 'free':
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

				if not pub_date and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
					try:
						pub_date = datetime.fromtimestamp(mktime(entry.updated_parsed))
					except (ValueError, OverflowError, OSError) as e:
						logger.warning('Invalid updated_parsed date', feed=self.title, error=str(e))

				if not pub_date:
					pub_date = datetime.now()
					logger.warning('Entry has no valid date, using current time', feed=self.title)

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

		return posts_added

	async def update_posts(self) -> bool:
		"""Update posts for this feed. Returns True if new content was added."""
		error_msg = None

		try:
			response = await fetch_feed(self.link, self.etag, self.modified)
			data: dict = await asyncio.to_thread(_parse_response, response)

			if data.bozo:
				bozo_msg = _bozo_message(data)
				logger.warning('Feed has formatting issues', feed=self.link, issue=bozo_msg)
				if not data.entries:
					raise FeedParsingError('Feed returned no entries due to parsing errors')

			with Session(engine) as session:
				posts_added = self._store_entries(data, session)

				# Single transaction: commit posts + update feed metadata
				feed = session.get(Feed, self.link)
				if feed:
					feed.last_success = datetime.now()
					feed.failure_count = 0
					feed.last_error = None
					feed.etag = response.headers.get('etag')
					feed.modified = response.headers.get('last-modified')

				try:
					session.commit()
					logger.info('Updated posts', feed=self.title, count=posts_added)
					return posts_added > 0
				except Exception as commit_exc:
					logger.error('Session commit failed', feed=self.title, error=str(commit_exc))
					session.rollback()
					raise

		except FeedNotModified:
			logger.debug('Feed not modified, skipping', feed=self.title)
			return False
		except httpx.HTTPError as e:
			error_msg = f'Connection error: {e}'
			logger.error('Connection failed', feed=self.link, error=str(e))
		except FeedParsingError as e:
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

		return False


class Post(SQLModel, table=True):
	__table_args__ = (Index('idx_post_publication_date', 'publication_date'),)

	link: str = Field(primary_key=True)
	title: str
	feed_link: str = Field(foreign_key='feed.link')
	feed: Feed = Relationship(back_populates='posts')
	publication_date: datetime
