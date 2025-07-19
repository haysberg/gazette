## BUILD STEP
FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS build
WORKDIR /build
RUN apt update -y && apt install imagemagick libpng-dev libjpeg-dev -y
COPY config.toml build.py uv.lock pyproject.toml .
RUN uv sync --frozen --no-cache --no-editable --compile-bytecode
COPY static ./static/
RUN uv run python build.py

## PROD STEP
FROM ghcr.io/astral-sh/uv:python3.13-alpine

ENV UV_COMPILE_BYTECODE="1"
ENV PATH="/app/.venv/bin:$PATH"
ENV TZ=Europe/Paris

WORKDIR /app

COPY config.toml app.py uv.lock pyproject.toml .
COPY templates ./templates/
COPY utils ./utils/
COPY --from=build /build/static ./static/
COPY --from=joseluisq/static-web-server:2-alpine /usr/local/bin/static-web-server /bin/static-web-server

RUN apk update --no-cache
RUN uv sync --frozen --no-cache --no-dev --no-editable --compile-bytecode


EXPOSE 8000

CMD ["python3", "app.py"]