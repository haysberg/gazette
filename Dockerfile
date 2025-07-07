# # Copy the application into the container.
# COPY config.toml main.py uv.lock pyproject.toml .
# COPY templates ./templates/
# COPY utils ./utils/
# COPY models ./models/
# COPY data ./data/

# Stage 0
# Installs dependencies and builds the application
# Artifacts will be copied to the final image
FROM alpine AS build

ARG PYTHON_VERSION="3.13"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin

ENV UV_COMPILE_BYTECODE="1"
ENV UV_LINK_MODE="copy"
ENV UV_PYTHON_INSTALL_DIR="/python"
ENV UV_PYTHON_PREFERENCE="only-managed"

WORKDIR /app

RUN uv python install $PYTHON_VERSION --no-cache
RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-cache --no-dev --no-editable --compile-bytecode

COPY config.toml app.py .
COPY templates ./templates/
COPY utils ./utils/
COPY static ./static/

# Stage 1
# Uses GoogleContainerTools/distroless as a minimal base
# Contains only necessary files and build artifacts
# Caching improves build speed
FROM python:3.13-alpine

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV TZ=Europe/Paris

COPY --from=build /python /python
COPY --from=build /app /app

RUN apk update && apk add cairo
CMD ["fastapi", "run", "app.py", "--port", "8000"]