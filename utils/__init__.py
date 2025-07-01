import os
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# Paths for static files
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
HTML_FILE = os.path.join(STATIC_DIR, "index.html")
PLUS_FILE = os.path.join(STATIC_DIR, "plus.html")
JSON_FILE = os.path.join(STATIC_DIR, "index.json")
TEMPLATES_DIR = "templates"