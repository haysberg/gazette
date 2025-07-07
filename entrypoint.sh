#!/bin/sh

python3 /app/.venv/bin/fastapi run app.py --port 8001 &
/bin/static-web-server