import os
import tomllib
from io import BytesIO

import requests
from PIL import Image

headers = {
	'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
}

with open('gazette.toml', 'rb') as f:
	content = f.read()
	config_data = tomllib.loads(content.decode('utf-8'))
	print(f'Found {len(config_data["feeds"]["feedlist"])} feeds in config.')
	for feed in config_data['feeds']['feedlist']:
		image_path = os.path.join(
			'static',
			'favicons',
			f'{feed["link"].split("/")[2].removeprefix("www.")}.avif',
		)
		os.makedirs(os.path.dirname(image_path), exist_ok=True)
		try:
			response = requests.get(feed['image'], timeout=10, headers=headers, stream=True)
			response.raise_for_status()
			img_data = BytesIO(response.content)
			Image.open(img_data).resize((32, 32)).save(image_path, 'AVIF')
		except Exception as e:
			print(f'Failed to process favicon for {feed["link"]}: {e}')
# Count all .avif images in static/favicons
avif_count = len(
	[
		name
		for name in os.listdir('static/favicons')
		if os.path.isfile(os.path.join('static/favicons', name)) and name.endswith('.avif')
	]
)
print(f'{avif_count} AVIF images in static/favicons.')

for root, dirs, files in os.walk('static/img'):
	for file in files:
		file_path = os.path.join(root, file)
		if file.endswith('.png'):
			# Open file and convert to AVIF
			image_path = file_path.rsplit('.', 1)[0] + '.avif'
			with open(file_path, 'rb') as f:
				file_content = f.read()
				Image.open(BytesIO(file_content)).resize((128, 128), Image.LANCZOS).save(
					image_path, 'AVIF'
				)
