import asyncio
import hashlib
import json
import os
import tomllib
from datetime import datetime, timedelta

import minify_html
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import selectinload
from sqlmodel import Session, delete, select

from precompress import write_compressed
from utils import CONFIG_FILE, HTML_FILE, RSS_FILE, STATIC_DIR, TEMPLATES_DIR, engine
from utils.logs import logger
from utils.models import Feed, Post

# Reuse a single Jinja2 environment across updates. Autoescaping is mandatory
# here: titles and subtitles come from third-party feeds, and rendering them raw
# lets a hostile or broken feed inject markup into the page.
_jinja_env = Environment(
	loader=FileSystemLoader(TEMPLATES_DIR),
	autoescape=select_autoescape(['html', 'xml']),
)
_jinja_env.filters['timeago'] = lambda dt: _timeago(dt)
_jinja_env.filters['rfc822'] = lambda dt: _rfc822(dt)
_jinja_env.filters['enclosure_type'] = lambda url: _enclosure_type(url)


def _file_hash(path: str) -> str:
	"""Return a short content hash for cache busting."""
	with open(path, 'rb') as f:
		return hashlib.md5(f.read()).hexdigest()[:8]


# Static asset hashes — these files only change at deploy time
_css_hash = _file_hash(f'{STATIC_DIR}/css/daisy.min.css')
_style_hash = _file_hash(f'{STATIC_DIR}/css/style.min.css')
_js_hash = _file_hash(f'{STATIC_DIR}/js/index.min.js')

# Per-source pages live in their own directory so the web server resolves
# /source/<domain>/ to the generated index.html.
SOURCE_DIR = os.path.join(STATIC_DIR, 'source')
STATUS_FILE = os.path.join(STATIC_DIR, 'status.json')

# How many posts a single source may show on the homepage. One prolific outlet
# (Reporterre, Révolution Permanente…) would otherwise dominate the flow. Set a
# feed's `max_display` to override per source, or 0 for unlimited.
DEFAULT_MAX_DISPLAY = 3


async def update_all_posts() -> None:
	logger.info('Updating posts')
	with Session(engine) as session:
		feeds = (session.exec(select(Feed))).all()

	# Skip feeds whose backoff window has not elapsed yet
	now = datetime.now()
	active_feeds = []
	for feed in feeds:
		if feed.next_retry is not None and feed.next_retry > now:
			logger.debug(
				'Feed in backoff, skipping',
				feed=feed.title,
				failure_count=feed.failure_count,
				retry_at=feed.next_retry.isoformat(),
			)
			continue
		active_feeds.append(feed)

	# return_exceptions keeps one unexpected failure from aborting the whole cycle.
	results = await asyncio.gather(
		*(feed.update_posts() for feed in active_feeds), return_exceptions=True
	)

	changed_feeds: set[str] = set()
	for feed, result in zip(active_feeds, results, strict=True):
		if isinstance(result, BaseException):
			logger.error('Feed update raised', feed=feed.title, error=str(result))
			continue
		if result:
			changed_feeds.add(feed.link)

	logger.info('Finished updating posts.', new_content=bool(changed_feeds))
	_prune_posts()
	_log_feed_health()

	# Regenerate the homepage/feed even without new content: the relative
	# timestamps drift after every cycle. Only feeds that changed get their
	# per-source page rebuilt (an empty set means none).
	await update_served_files(changed_feeds)


def _prune_posts() -> None:
	"""Drop entries older than a week and enforce each feed's max_posts throttle."""
	with Session(engine) as session:
		logger.debug('Running cleanup of old posts...')
		statement = delete(Post).where(Post.publication_date < datetime.now() - timedelta(weeks=1))
		session.exec(statement)

		feeds_with_limit = session.exec(select(Feed).where(Feed.max_posts.is_not(None))).all()
		for feed in feeds_with_limit:
			excess_posts = session.exec(
				select(Post)
				.where(Post.feed_link == feed.link)
				.order_by(Post.publication_date.desc())
				.offset(feed.max_posts)
			).all()
			for post in excess_posts:
				session.delete(post)

		session.commit()


def _log_feed_health() -> None:
	"""Log a one-line summary, naming every feed that is currently failing."""
	with Session(engine) as session:
		feeds = session.exec(select(Feed)).all()

	failing = [f for f in feeds if f.failure_count > 0]
	if failing:
		logger.warning(
			'Feeds failing',
			count=len(failing),
			total=len(feeds),
			feeds=[f.title for f in failing],
		)
	else:
		logger.info('All feeds healthy', total=len(feeds))


def _rfc822(dt: datetime) -> str:
	"""Render a local datetime as an RFC 822 timestamp with its real offset.

	The pubDate used to be formatted with a literal `+0000` even though the value
	was local time, so every item's timestamp was off by the UTC offset.
	"""
	return dt.astimezone().strftime('%a, %d %b %Y %H:%M:%S %z')


def _enclosure_type(url: str) -> str:
	"""Best-effort MIME type for a feed entry image, from its file extension."""
	extension = os.path.splitext(url.split('?', 1)[0])[1].lower()
	return {
		'.png': 'image/png',
		'.webp': 'image/webp',
		'.avif': 'image/avif',
		'.gif': 'image/gif',
	}.get(extension, 'image/jpeg')


def _timeago(dt: datetime) -> str:
	delta = datetime.now() - dt
	seconds = int(delta.total_seconds())
	if seconds < 60:
		return "À l'instant"
	minutes = seconds // 60
	if minutes < 60:
		return f'Il y a {minutes} min'
	hours = minutes // 60
	if hours < 24:
		return f'Il y a {hours}h'
	days = hours // 24
	return f'Il y a {days}j'


def _apply_display_cap(posts: list[Post]) -> list[Post]:
	"""Keep at most each feed's `max_display` newest posts (0 = unlimited).

	`posts` is expected newest-first; a feed that published a burst keeps only
	its most recent few on the homepage.
	"""
	counts: dict[str, int] = {}
	kept: list[Post] = []
	for post in posts:
		limit = post.feed.max_display
		if limit is None:
			limit = DEFAULT_MAX_DISPLAY
		if limit > 0:
			seen = counts.get(post.feed_link, 0)
			if seen >= limit:
				continue
			counts[post.feed_link] = seen + 1
		kept.append(post)
	return kept


async def update_served_files(changed_feeds: set[str] | None = None) -> None:
	"""Render every served page.

	`changed_feeds` (None = all) limits which per-source pages are rebuilt: the
	homepage and the RSS feed are always regenerated so relative timestamps and
	pruning stay current even when no feed reported anything new.
	"""
	logger.info('Generating static files...')

	with Session(engine) as session:
		now = datetime.now()
		statement = (
			select(Post)
			.options(selectinload(Post.feed))
			.where(Post.publication_date > now - timedelta(hours=48))
			.order_by(Post.publication_date.desc())
		)
		posts_last48h: list[Post] = session.exec(statement).all()

		# The RSS feed keeps the last 24h in full; the homepage per-source cap is
		# a display concern, so it is applied only to what is split into days.
		posts_24h = [p for p in posts_last48h if p.publication_date > now - timedelta(hours=24)]
		posts_today: list[Post] = []
		posts_yesterday: list[Post] = []
		today_date = now.date()
		for post in _apply_display_cap(posts_last48h):
			if post.publication_date.date() == today_date:
				posts_today.append(post)
			else:
				posts_yesterday.append(post)

		feeds = (session.exec(select(Feed).order_by(Feed.title.desc()))).all()

		week_statement = (
			select(Post)
			.options(selectinload(Post.feed))
			.where(Post.publication_date > now - timedelta(weeks=1))
			.order_by(Post.publication_date.desc())
		)
		posts_by_feed: dict[str, list[Post]] = {}
		for post in session.exec(week_statement).all():
			posts_by_feed.setdefault(post.feed_link, []).append(post)

		try:
			index_html = _jinja_env.get_template('index.html').render(
				posts_today=posts_today,
				posts_yesterday=posts_yesterday,
				plus=True,
				css_hash=_css_hash,
				style_hash=_style_hash,
				js_hash=_js_hash,
				canonical_url='https://insoumis.news/',
				is_home=True,
			)
			rss_xml = _jinja_env.get_template('feed.xml').render(
				posts=posts_24h,
				build_date=now,
			)

			# minify_js does the work; CSS is not re-minified because the external
			# stylesheets are already compressed and fingerprinted at build time.
			index_html = minify_html.minify(index_html, minify_css=False, minify_js=True)

			# The RSS feed is deliberately NOT minified: minify_html applies HTML rules
			# to XML, which unquotes attributes (version=2.0), lowercases tags
			# (lastBuildDate) and drops </link> because <link> is a void HTML element.
			# That produced a feed that was not well-formed XML. Brotli already squeezes
			# out the whitespace, so there is nothing to gain here.

			# Per-source pages. Only rebuild the ones whose feed changed, unless the
			# caller asked for a full render (startup, config change).
			source_template = _jinja_env.get_template('source.html')
			source_pages: list[tuple[str, str]] = []
			for feed in feeds:
				if changed_feeds is not None and feed.link not in changed_feeds:
					continue
				page = source_template.render(
					feed=feed,
					posts=posts_by_feed.get(feed.link, []),
					css_hash=_css_hash,
					style_hash=_style_hash,
					js_hash=_js_hash,
					canonical_url=f'https://insoumis.news/source/{feed.domain}/',
				)
				page = minify_html.minify(page, minify_css=False, minify_js=True)
				source_pages.append(
					(os.path.join(SOURCE_DIR, feed.domain, 'index.html'), page)
				)

			status_json = json.dumps(
				_build_status(feeds, posts_by_feed, now), ensure_ascii=False, indent=2
			)

			logger.debug('Pages rendered successfully')
		except Exception as e:
			logger.error('Failed to render template', error=str(e))
			return

	# Write each page with its brotli/gzip siblings. Without them the web server
	# compresses from scratch on every request; here it is paid once per
	# regeneration. Brotli q11 is CPU-bound, so it runs in threads rather than
	# stalling the scheduler's event loop.
	for feed in feeds:
		if changed_feeds is None or feed.link in changed_feeds:
			os.makedirs(os.path.join(SOURCE_DIR, feed.domain), exist_ok=True)

	pages = [(HTML_FILE, index_html), (RSS_FILE, rss_xml), (STATUS_FILE, status_json)]
	pages.extend(source_pages)
	await _write_pages(pages)

	logger.debug('Static files generation ended.')


def _build_status(
	feeds: list[Feed], posts_by_feed: dict[str, list[Post]], now: datetime
) -> dict:
	"""Machine-readable feed health snapshot, written to /status.json."""
	return {
		'generated_at': now.isoformat(),
		'feeds_total': len(feeds),
		'feeds_failing': [feed.title for feed in feeds if feed.failure_count > 0],
		'feeds': [
			{
				'title': feed.title,
				'domain': feed.domain,
				'link': feed.link,
				'failure_count': feed.failure_count,
				'last_error': feed.last_error,
				'last_success': feed.last_success.isoformat() if feed.last_success else None,
				'next_retry': feed.next_retry.isoformat() if feed.next_retry else None,
				'post_count': len(posts_by_feed.get(feed.link, [])),
			}
			for feed in feeds
		],
	}


async def _write_pages(pages: list[tuple[str, str]]) -> None:
	"""Write pages concurrently, logging rather than raising on a single failure."""
	results = await asyncio.gather(
		*(asyncio.to_thread(write_compressed, path, data) for path, data in pages),
		return_exceptions=True,
	)
	for (path, _), result in zip(pages, results, strict=True):
		if isinstance(result, BaseException):
			logger.error('Failed to save file', path=path, error=str(result))


async def init_service() -> None:
	with open(CONFIG_FILE, 'rb') as f:
		config_data = tomllib.load(f)
		logger.debug('Found feeds', count=len(config_data['feeds']['feedlist']))

	logger.info('Initializing feeds...')
	feedlist = config_data['feeds']['feedlist']
	results = await asyncio.gather(
		*(Feed.init_feed(feed_dict) for feed_dict in feedlist), return_exceptions=True
	)

	total = len(feedlist)
	succeeded = sum(1 for r in results if r is not None and not isinstance(r, BaseException))
	failed = total - succeeded
	logger.info('Feed initialization complete', total=total, succeeded=succeeded, failed=failed)

	# Enforce max_posts/cleanup now: otherwise a feed with hundreds of entries is
	# fully rendered until the scheduler's first interval, 15 minutes out.
	_prune_posts()
	_log_feed_health()

	# init_feed already stored the entries from its own fetch, so the pages can be
	# rendered right away. The scheduler's first run is therefore one interval out
	# instead of immediately re-fetching every feed.
	await update_served_files()
