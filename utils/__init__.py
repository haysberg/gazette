import os

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

engine = create_engine(
	'sqlite:///:memory:',
	echo=False,
	connect_args={'check_same_thread': False},
	poolclass=StaticPool,
)

# Paths for static files
STATIC_DIR = 'static'
os.makedirs(STATIC_DIR, exist_ok=True)
HTML_FILE = os.path.join(STATIC_DIR, 'index.html')
RSS_FILE = os.path.join(STATIC_DIR, 'feed.xml')
TEMPLATES_DIR = 'templates'
