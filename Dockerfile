## PROD STEP
FROM ghcr.io/astral-sh/uv:python3.13-alpine
ENV PATH="/app/.venv/bin:$PATH"
ENV TZ=Europe/Paris

WORKDIR /app

COPY config.toml app.py uv.lock pyproject.toml .
COPY templates ./templates/
COPY utils ./utils/
COPY static ./static/
COPY --from=joseluisq/static-web-server:2-alpine /usr/local/bin/static-web-server /bin/static-web-server

RUN apk update --no-cache && apk add cairo-dev && uv sync --frozen --no-cache --no-dev --no-editable --compile-bytecode

EXPOSE 8000

CMD ["python3", "app.py"]