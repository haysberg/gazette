# Stage 0
# Installs dependencies and builds the application
# Artifacts will be copied to the final image
FROM ghcr.io/astral-sh/uv:python3.13-alpine

ENV UV_COMPILE_BYTECODE="1"
ENV PATH="/app/.venv/bin:$PATH"
ENV TZ=Europe/Paris

WORKDIR /app

COPY config.toml app.py uv.lock uv.lock pyproject.toml .
COPY templates ./templates/
COPY utils ./utils/
COPY static ./static/
COPY --from=joseluisq/static-web-server:2-alpine /usr/local/bin/static-web-server /bin/static-web-server

RUN uv sync --frozen --no-cache --no-dev --no-editable --compile-bytecode
RUN apk update && apk add cairo

EXPOSE 8000

CMD ["fastapi", "run", "--host", "127.0.0.1", "--port", "8001"]