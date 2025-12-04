# import os
import tomllib

# from io import BytesIO
from jinja2 import Environment, FileSystemLoader

# Initialize Jinja2 environment
env = Environment(loader=FileSystemLoader('templates'))

with open('gazette.toml', 'rb') as f:
	content = f.read()
	config_data = tomllib.loads(content.decode('utf-8'))
	print(f'Found {len(config_data["feeds"]["feedlist"])} feeds in config.')
	# Render index.html
	template = env.get_template('feeds.opml')
	opml_content = template.render(feeds=config_data['feeds']['feedlist'])
	with open('./static/feeds.opml', 'w') as o:
		o.write(opml_content)
	print('OPML rendered successfully !')
