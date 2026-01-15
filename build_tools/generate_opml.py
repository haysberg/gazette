import tomllib

from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'), autoescape=True)

with open('gazette.toml', 'rb') as f:
	content = f.read()
	config_data = tomllib.loads(content.decode('utf-8'))
	feeds = config_data['feeds']['feedlist']
	print(f'Found {len(feeds)} feeds in config.')

	# Render OPML
	opml_template = env.get_template('feeds.opml')
	opml_content = opml_template.render(feeds=feeds)
	with open('./static/feeds.opml', 'w', encoding='utf-8') as o:
		o.write(opml_content)
	print('OPML rendered successfully!')

	# Render sources page
	sources_template = env.get_template('sources.html')
	sources_content = sources_template.render(feeds=feeds)
	with open('./static/sources.html', 'w', encoding='utf-8') as o:
		o.write(sources_content)
	print('Sources page rendered successfully!')
