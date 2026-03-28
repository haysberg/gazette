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
COPY gazette.toml uv.lock pyproject.toml ./
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

COPY gazette.toml sws.toml app.py uv.lock pyproject.toml ./
COPY templates ./templates/
COPY --from=build /build/templates/inline_style.html ./templates/inline_style.html
COPY utils ./utils/
COPY --from=build /build/static ./static/
COPY --from=ghcr.io/static-web-server/static-web-server /static-web-server /bin/static-web-server

RUN apk update --no-cache && apk add --no-cache curl && uv sync --frozen --no-cache --no-dev --no-editable --compile-bytecode

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
	CMD curl -f http://localhost:8000/ || exit 1

CMD ["python3", "app.py"]
