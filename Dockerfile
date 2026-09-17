## CSS BUILD STEP
FROM oven/bun:alpine AS css-build
WORKDIR /build
COPY package.json ./
RUN bun install
COPY src/ ./src/
COPY templates/ ./templates/
RUN bunx @tailwindcss/cli -i src/tailwind.css -o static/css/daisy.min.css --minify

## PYTHON BUILD STEP
FROM ghcr.io/astral-sh/uv:python3.14-alpine AS build
WORKDIR /build
COPY gazette.toml uv.lock pyproject.toml precompress.py ./
COPY static ./static/
COPY templates ./templates/
COPY build_tools ./build_tools/
COPY --from=css-build /build/static/css/daisy.min.css ./static/css/daisy.min.css
RUN uv run ./build_tools/convert_icons.py \
    && uv run ./build_tools/compress_all.py \
    && uv run ./build_tools/generate_opml.py

## PROD STEP
FROM ghcr.io/astral-sh/uv:python3.14-alpine
ENV PATH="/app/.venv/bin:$PATH"
ENV TZ=Europe/Paris

WORKDIR /app

COPY gazette.toml sws.toml app.py uv.lock pyproject.toml precompress.py ./
COPY templates ./templates/
COPY --from=build /build/templates/inline_style.html ./templates/inline_style.html
COPY utils ./utils/
COPY --from=build /build/static ./static/
COPY --from=ghcr.io/static-web-server/static-web-server /static-web-server /bin/static-web-server

RUN uv sync --frozen --no-cache --no-dev --no-editable --compile-bytecode \
	&& addgroup -S gazette \
	&& adduser -S -G gazette gazette \
	&& chown -R gazette:gazette /app

# The app renders pages into /app/static at runtime, so that tree must stay
# writable by the unprivileged user; everything else is read-only.
USER gazette

EXPOSE 8000

# /healthz is a static file: a full homepage render should not be the liveness
# probe. busybox wget is part of the base image, so curl is not needed.
# Probe 127.0.0.1, not localhost: static-web-server binds IPv4 only, while
# localhost resolves to ::1 first in the image and yields a false negative.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
	CMD wget -q -O /dev/null http://127.0.0.1:8000/healthz || exit 1

CMD ["python3", "app.py"]
