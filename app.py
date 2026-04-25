import asyncio
import signal
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

	loop = asyncio.get_running_loop()

	# Handle graceful shutdown
	stop_event = asyncio.Event()

	def shutdown_handler():
		logger.info('Received shutdown signal, stopping...')
		scheduler.shutdown(wait=False)
		stop_event.set()

	for sig in (signal.SIGTERM, signal.SIGINT):
		loop.add_signal_handler(sig, shutdown_handler)

	# Start static-web-server as a monitored async subprocess
	server_process = await asyncio.create_subprocess_exec('/bin/static-web-server')

	async def monitor_server():
		"""Shut down the app if the web server exits unexpectedly."""
		returncode = await server_process.wait()
		if not stop_event.is_set():
			logger.error('static-web-server exited unexpectedly', returncode=returncode)
			stop_event.set()

	monitor_task = asyncio.create_task(monitor_server())

	try:
		await stop_event.wait()
	finally:
		if server_process.returncode is None:
			server_process.terminate()
			await server_process.wait()
		monitor_task.cancel()
		logger.info('Shutdown complete')


if __name__ == '__main__':
	asyncio.run(main())
