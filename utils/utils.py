import asyncio
import tomllib
from datetime import datetime, timedelta

import aiofiles
import minify_html
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import selectinload
from sqlmodel import Session, delete, select

from utils import HTML_FILE, RSS_FILE, STATIC_DIR, TEMPLATES_DIR, engine
from utils.logs import logger
from utils.models import Feed, Post

# Skip feeds that have failed more than this many times in a row
MAX_CONSECUTIVE_FAILURES = 10


async def update_all_posts() -> None:
	logger.info('Updating posts')
	with Session(engine) as session:
		feeds = (session.exec(select(Feed))).all()

	# Skip feeds with too many consecutive failures
	active_feeds = []
	for feed in feeds:
		if feed.failure_count >= MAX_CONSECUTIVE_FAILURES:
			logger.warning(
				'Skipping feed due to repeated failures',
				feed=feed.title,
				failure_count=feed.failure_count,
			)
			continue
		active_feeds.append(feed)

	tasks = [feed.update_posts() for feed in active_feeds]
	await asyncio.gather(*tasks)
	logger.info('Finished updating posts.')

	# Delete entries older than a week
	with Session(engine) as session:
		logger.debug('Running cleanup of old posts...')
		statement = delete(Post).where(Post.publication_date < datetime.now() - timedelta(weeks=1))
		session.exec(statement)

		# Throttle feeds with max_posts limit
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
	await update_served_files()


def timeago(dt: datetime) -> str:
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


async def update_served_files() -> None:
	logger.info('Generating static files...')

	env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
	env.filters['timeago'] = timeago

	with Session(engine) as session:
		# Get posts from the last 24 hours
		statement = (
			select(Post)
			.options(selectinload(Post.feed))
			.where(Post.publication_date > datetime.now() - timedelta(days=1))
			.order_by(Post.publication_date.desc())
		)
		posts_last24h: list[Post] = session.exec(statement).all()

		# Split posts from the last 24 hours into today and yesterday
		posts_today: list[Post] = []
		posts_yesterday: list[Post] = []
		today_date = datetime.now().date()

		for post in posts_last24h:
			if post.publication_date.date() == today_date:
				posts_today.append(post)
			else:
				posts_yesterday.append(post)

		# Get all feeds
		feeds = (session.exec(select(Feed).order_by(Feed.title.desc()))).all()

		try:
			template = env.get_template('index.html')
			index_html = template.render(
				posts_today=posts_today,
				posts_yesterday=posts_yesterday,
				feeds=feeds,
				plus=True,
			)

			rss_template = env.get_template('feed.xml')
			rss_xml = rss_template.render(
				posts=posts_last24h,
				build_date=datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
			)

			index_html = minify_html.minify(index_html, minify_css=True, minify_js=True)
			rss_xml = minify_html.minify(rss_xml)

			logger.debug('Pages rendered successfully')
		except Exception as e:
			logger.error('Failed to render template', error=str(e))
			return

	try:
		async with aiofiles.open(HTML_FILE, 'w') as f:
			await f.write(index_html)
		logger.debug('HTML file saved', path=HTML_FILE)

		async with aiofiles.open(RSS_FILE, 'w') as f:
			await f.write(rss_xml)
		logger.debug('RSS feed saved', path=RSS_FILE)

	except Exception as e:
		logger.error('Failed to save file', error=str(e))

	logger.debug('Static files generation ended.')


async def init_service() -> None:
	with open('gazette.toml', 'rb') as f:
		config_data = tomllib.load(f)
		logger.debug('Found feeds', count=len(config_data['feeds']['feedlist']))

	logger.info('Initializing feeds...')
	tasks = [Feed.init_feed(feed_dict) for feed_dict in config_data['feeds']['feedlist']]
	await asyncio.gather(*tasks)
