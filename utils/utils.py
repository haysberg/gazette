import asyncio
import json
import os
import tomllib
from datetime import datetime, timedelta

import aiofiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import selectinload
from sqlmodel import Session, delete, select

from utils import HTML_FILE, JSON_FILE, PLUS_FILE, STATIC_DIR, TEMPLATES_DIR, engine
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

	posts_last24h: list[Post] = []
	posts_later: list[Post] = []

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
		feeds = (session.exec(select(Feed).order_by(Feed.title.desc()))).all()
		render_time = datetime.now().strftime('%Hh%M').capitalize()

		# Render Jinja2 template and save as HTML
		try:
			# Render index.html
			template = env.get_template('index.html')
			index_html = template.render(
				posts=posts_last24h,
				feeds=feeds,
				plus=True,
				render_time=render_time,
			)

			# Render plus.html
			plus_html = template.render(
				posts=posts_later,
				feeds=feeds,
				plus=False,
				render_time=render_time,
			)

			# Generate JSON and save as a file
			json_data = {
				'posts_last24h': [post.model_dump() for post in posts_last24h],
				'posts_later': [post.model_dump() for post in posts_later],
				'feeds': [feed.model_dump() for feed in feeds],
			}
			logger.debug('Pages rendered successfully !')
		except Exception as e:
			logger.error(f'Failed to render template: {e}')
			return

	try:
		async with aiofiles.open(HTML_FILE, 'w') as f:
			await f.write(index_html)
		logger.debug(f'HTML file saved to {HTML_FILE}')

		async with aiofiles.open(PLUS_FILE, 'w') as f:
			await f.write(plus_html)
		logger.debug(f'PLUS file saved to {PLUS_FILE}')

		async with aiofiles.open(JSON_FILE, 'w') as f:
			await f.write(json.dumps(json_data, sort_keys=True, default=str))
		logger.debug(f'JSON file saved to {JSON_FILE}')

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
