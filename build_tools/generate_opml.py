import hashlib
import os
import sys
import tomllib

from jinja2 import Environment, FileSystemLoader

# Run as a script, so the repo root is not on sys.path — add it to reach precompress.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from precompress import write_compressed  # noqa: E402

env = Environment(loader=FileSystemLoader('templates'), autoescape=True)


def file_hash(path: str) -> str:
	with open(path, 'rb') as f:
		return hashlib.md5(f.read()).hexdigest()[:8]


with open('gazette.toml', 'rb') as f:
	content = f.read()
	config_data = tomllib.loads(content.decode('utf-8'))
	feeds = config_data['feeds']['feedlist']
	print(f'Found {len(feeds)} feeds in config.')

	css_hash = file_hash('static/css/daisy.min.css')
	style_hash = file_hash('static/css/style.min.css')
	js_hash = file_hash('static/js/index.min.js')

	# Render OPML
	opml_template = env.get_template('feeds.opml')
	opml_content = opml_template.render(feeds=feeds)
	write_compressed('./static/feeds.opml', opml_content)
	print('OPML rendered successfully!')

	# Render sources page
	sources_template = env.get_template('sources.html')
	sources_content = sources_template.render(
		feeds=feeds,
		css_hash=css_hash,
		style_hash=style_hash,
		js_hash=js_hash,
		canonical_url='https://insoumis.news/sources.html',
	)
	write_compressed('./static/sources.html', sources_content)
	print('Sources page rendered successfully!')

	# Render privacy page
	privacy_template = env.get_template('privacy.html')
	privacy_content = privacy_template.render(
		css_hash=css_hash,
		style_hash=style_hash,
		js_hash=js_hash,
		canonical_url='https://insoumis.news/privacy.html',
	)
	write_compressed('./static/privacy.html', privacy_content)
	print('Privacy page rendered successfully!')

	# Render sitemap, including one entry per per-source page
	sitemap_template = env.get_template('sitemap.xml')
	sitemap_content = sitemap_template.render(feeds=feeds)
	write_compressed('./static/sitemap.xml', sitemap_content)
	print('Sitemap rendered successfully!')

	# Render /llms-full.txt — full content dump for AI agents
	llms_full_template = env.get_template('llms-full.txt')
	llms_full_content = llms_full_template.render(feeds=feeds)
	write_compressed('./static/llms-full.txt', llms_full_content)
	print('llms-full.txt rendered successfully!')
