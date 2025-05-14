FROM ghcr.io/astral-sh/uv:alpine

RUN apk add --no-cache tzdata
ENV TZ=Europe/Paris

WORKDIR /app

# Copy the application into the container.
COPY config.toml main.py uv.lock pyproject.toml .
COPY templates ./templates/
COPY utils ./utils/
COPY models ./models/
COPY static ./static/


RUN uv sync --frozen --no-cache --no-dev

# Run the application.
CMD ["/app/.venv/bin/fastapi", "run", "main.py", "--port", "80", "--host", "0.0.0.0"]