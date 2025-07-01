import logging
import structlog
import os

LOGLEVEL = os.getenv("LOGLEVEL", "INFO").upper()


def configure_logging():
    # Define a shared processor chain for structlog
    processors = [
        structlog.stdlib.PositionalArgumentsFormatter(),  # Format positional args
        structlog.processors.StackInfoRenderer(),  # Add stack info if available
        structlog.dev.ConsoleRenderer(colors=True),  # Pretty, human-readable logs
    ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(LOGLEVEL),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Redirect standard logging to structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),  # Pretty logs
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,  # Include log level in logs
            structlog.stdlib.PositionalArgumentsFormatter(),  # Format positional args
            structlog.processors.StackInfoRenderer(),  # Add stack info if available
            structlog.processors.TimeStamper(
                fmt="iso", utc=False
            ),  # Add ISO 8601 timestamps
        ],
    )

    # Set up the root logger
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(
        handlers=[handler],
        level=LOGLEVEL,
    )

    # Ensure structlog logs bypass logging module formatting
    structlog_logger = logging.getLogger("structlog")
    structlog_logger.propagate = False  # Prevent structlog logs from being reprocessed

    # Redirect Uvicorn logs to structlog
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = [handler]
    uvicorn_logger.propagate = False

    # Redirect SQLAlchemy logs to structlog
    logging.getLogger("sqlalchemy.engine").setLevel(LOGLEVEL)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    if LOGLEVEL != "DEBUG":
        logging.getLogger("sqlalchemy.engine").setLevel(logging.NOTSET)
    logging.getLogger().setLevel(LOGLEVEL)


logger = structlog.get_logger()
