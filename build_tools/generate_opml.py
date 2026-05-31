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

	with open('static/csp-hash.txt') as csp_file:
		csp_hash = csp_file.read().strip()

	# Render OPML
	opml_template = env.get_template('feeds.opml')
	opml_content = opml_template.render(feeds=feeds)
	with open('./static/feeds.opml', 'w', encoding='utf-8') as o:
		o.write(opml_content)
	print('OPML rendered successfully!')

	# Render sources page
	sources_template = env.get_template('sources.html')
	sources_content = sources_template.render(
		feeds=feeds,
		css_hash=css_hash,
		js_hash=js_hash,
		canonical_url='https://insoumis.news/sources.html',
		csp_hash=csp_hash,
	)
	with open('./static/sources.html', 'w', encoding='utf-8') as o:
		o.write(sources_content)
	print('Sources page rendered successfully!')

	# Render privacy page
	privacy_template = env.get_template('privacy.html')
	privacy_content = privacy_template.render(
		css_hash=css_hash,
		js_hash=js_hash,
		canonical_url='https://insoumis.news/privacy.html',
		csp_hash=csp_hash,
	)
	with open('./static/privacy.html', 'w', encoding='utf-8') as o:
		o.write(privacy_content)
	print('Privacy page rendered successfully!')

	# Render /llms-full.txt — full content dump for AI agents
	llms_full_template = env.get_template('llms-full.txt')
	llms_full_content = llms_full_template.render(feeds=feeds)
	with open('./static/llms-full.txt', 'w', encoding='utf-8') as o:
		o.write(llms_full_content)
	print('llms-full.txt rendered successfully!')
