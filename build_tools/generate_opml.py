import hashlib
import tomllib

from jinja2 import Environment, FileSystemLoader

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
	js_hash = file_hash('static/js/index.min.js')

	# Render OPML
	opml_template = env.get_template('feeds.opml')
	opml_content = opml_template.render(feeds=feeds)
	with open('./static/feeds.opml', 'w', encoding='utf-8') as o:
		o.write(opml_content)
	print('OPML rendered successfully!')

	# Render sources page
	sources_template = env.get_template('sources.html')
	sources_content = sources_template.render(feeds=feeds, css_hash=css_hash, js_hash=js_hash)
	with open('./static/sources.html', 'w', encoding='utf-8') as o:
		o.write(sources_content)
	print('Sources page rendered successfully!')
