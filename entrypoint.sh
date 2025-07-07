#!/bin/sh

/bin/static-web-server &
sleep 2
python3 /app/.venv/bin/fastapi run app.py --port 8001