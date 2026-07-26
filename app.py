import asyncio
import os
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import SQLModel

from utils import engine
from utils.logs import configure_logging, logger
from utils.models import close_client
from utils.utils import init_service, update_all_posts

# The container image bundles static-web-server. Set GAZETTE_SERVE_STATIC=0 when an
# external server (Caddy, nginx) already serves STATIC_DIR, so this process only
# runs the feed scheduler.
SERVE_STATIC = os.environ.get('GAZETTE_SERVE_STATIC', '1') != '0'
UPDATE_INTERVAL_MINUTES = int(os.environ.get('GAZETTE_UPDATE_MINUTES', '15'))

configure_logging()
SQLModel.metadata.create_all(bind=engine)


async def main():
	# Populates the feeds and renders the first pages, so no immediate scheduler
	# run is needed: the first interval fire is UPDATE_INTERVAL_MINUTES from now.
	await init_service()

	scheduler = AsyncIOScheduler()
	scheduler.add_job(
		update_all_posts,
		'interval',
		minutes=UPDATE_INTERVAL_MINUTES,
		max_instances=1,
	)
	scheduler.start()

	loop = asyncio.get_running_loop()

	# Handle graceful shutdown
	stop_event = asyncio.Event()

	def shutdown_handler():
		# Guard against a second signal: shutting the scheduler down twice raises
		# SchedulerNotRunningError out of the handler.
		if stop_event.is_set():
			return
		logger.info('Received shutdown signal, stopping...')
		scheduler.shutdown(wait=False)
		stop_event.set()

	for sig in (signal.SIGTERM, signal.SIGINT):
		loop.add_signal_handler(sig, shutdown_handler)

	server_process = None
	monitor_task = None

	if SERVE_STATIC:
		# Start static-web-server as a monitored async subprocess
		server_process = await asyncio.create_subprocess_exec('/bin/static-web-server')

		async def monitor_server():
			"""Shut down the app if the web server exits unexpectedly."""
			returncode = await server_process.wait()
			if not stop_event.is_set():
				logger.error('static-web-server exited unexpectedly', returncode=returncode)
				stop_event.set()

		monitor_task = asyncio.create_task(monitor_server())
	else:
		logger.info('Serving static files externally, running scheduler only')

	try:
		await stop_event.wait()
	finally:
		if server_process is not None and server_process.returncode is None:
			server_process.terminate()
			await server_process.wait()
		if monitor_task is not None:
			monitor_task.cancel()
		await close_client()
		logger.info('Shutdown complete')


if __name__ == '__main__':
	asyncio.run(main())
