import asyncio
import signal
import subprocess
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import SQLModel

from utils import engine
from utils.logs import configure_logging, logger
from utils.utils import init_service, update_all_posts

configure_logging()
SQLModel.metadata.create_all(bind=engine)


async def main():
	await init_service()

	scheduler = AsyncIOScheduler()
	scheduler.add_job(
		update_all_posts,
		'interval',
		minutes=15,
		max_instances=1,
		next_run_time=datetime.now(),
	)
	scheduler.start()

	# Run static-web-server in a separate process
	# Use asyncio.to_thread to avoid blocking the event loop
	loop = asyncio.get_running_loop()

	# Handle graceful shutdown
	stop_event = asyncio.Event()

	def shutdown_handler():
		logger.info('Received shutdown signal, stopping...')
		scheduler.shutdown(wait=False)
		stop_event.set()

	for sig in (signal.SIGTERM, signal.SIGINT):
		loop.add_signal_handler(sig, shutdown_handler)

	# Start static-web-server in a thread
	server_process = await asyncio.to_thread(subprocess.Popen, ['/bin/static-web-server'])

	try:
		# Wait until shutdown signal
		await stop_event.wait()
	finally:
		server_process.terminate()
		server_process.wait()
		logger.info('Shutdown complete')


if __name__ == '__main__':
	asyncio.run(main())
