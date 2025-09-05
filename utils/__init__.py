import os

from sqlmodel import create_engine

engine = create_engine('sqlite:///gazette.db', echo=False)

# Paths for static files
STATIC_DIR = 'static'
os.makedirs(STATIC_DIR, exist_ok=True)
HTML_FILE = os.path.join(STATIC_DIR, 'index.html')
SOURCES_FILE = os.path.join(STATIC_DIR, 'sources.html')
PLUS_FILE = os.path.join(STATIC_DIR, 'plus.html')
JSON_FILE = os.path.join(STATIC_DIR, 'index.json')
TEMPLATES_DIR = 'templates'
