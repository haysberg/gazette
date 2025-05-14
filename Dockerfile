FROM ghcr.io/astral-sh/uv:alpine

# Copy the application into the container.
COPY config.toml main.py uv.lock pyproject.toml /app
COPY templates /app/templates
COPY utils /app/utils
COPY models /app/models
COPY static /app/static

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen --no-cache --no-dev

# Run the application.
CMD ["/app/.venv/bin/fastapi", "run", "main.py", "--port", "80", "--host", "0.0.0.0"]