import asyncio
import subprocess
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import SQLModel

from utils import engine
from utils.logs import configure_logging
from utils.utils import init_service, update_all_posts

configure_logging()
SQLModel.metadata.create_all(bind=engine)


async def main():
	await init_service()
	scheduler = BackgroundScheduler()

	def run_update_all_posts():
		asyncio.run(update_all_posts())

	_ = scheduler.add_job(
		run_update_all_posts,
		'interval',
		minutes=15,
		max_instances=1,
		next_run_time=datetime.now(),
	)
	scheduler.start()
	subprocess.run(['/bin/static-web-server'])


if __name__ == '__main__':
	asyncio.run(main())
