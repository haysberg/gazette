import asyncio
import os
import tomllib
from datetime import datetime, timedelta

import aiofiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import selectinload
from sqlmodel import Session, delete, select

from utils import HTML_FILE, STATIC_DIR, TEMPLATES_DIR, engine
from utils.logs import logger
from utils.models import Feed, Post


async def update_all_posts() -> None:
	logger.info('Updating posts')
	with Session(engine) as session:
		feeds = (session.exec(select(Feed))).all()
	tasks = [feed.update_posts() for feed in feeds]
	await asyncio.gather(*tasks)
	logger.info('Finished updating posts.')

	# Delete entries older than a week
	with Session(engine) as session:
		# Delete entries in db older than a week
		logger.debug('Running cleanup of old posts...')
		statement = delete(Post).where(Post.publication_date < datetime.now() - timedelta(weeks=1))
		session.exec(statement)
		session.commit()
	await update_served_files()


async def update_served_files() -> None:
	logger.info('Generating static files...')
	os.makedirs(STATIC_DIR, exist_ok=True)

	# Initialize Jinja2 environment
	env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

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

		# Render Jinja2 template and save as HTML
		try:
			# Render index.html
			template = env.get_template('index.html')
			index_html = template.render(
				posts_today=posts_today,
				posts_yesterday=posts_yesterday,
				feeds=feeds,
				plus=True,
			)

			logger.debug('Pages rendered successfully !')
		except Exception as e:
			logger.error(f'Failed to render template: {e}')
			return

	try:
		async with aiofiles.open(HTML_FILE, 'w') as f:
			await f.write(index_html)
		logger.debug(f'HTML file saved to {HTML_FILE}')

	except Exception as e:
		logger.error(f'Failed to save file: {e}')

	logger.debug('Static files generation ended.')


async def init_service() -> None:
	with open('gazette.toml', 'rb') as f:
		content = f.read()
		config_data = tomllib.loads(content.decode('utf-8'))
		logger.debug(f'Found {len(config_data["feeds"]["feedlist"])} feeds')

	logger.info('Initializing feeds...')
	tasks = [Feed.init_feed(feed_dict) for feed_dict in config_data['feeds']['feedlist']]
	await asyncio.gather(*tasks)
