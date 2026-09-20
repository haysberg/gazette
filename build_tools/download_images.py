import os
import subprocess
import sys
import tomllib
from io import BytesIO

import cairosvg
import requests
from PIL import Image

headers = {
	'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
}

SMALL_SIZE = (32, 32)
# Source logos are shown at 48 CSS px, so ~128 px still covers HiDPI phones
# while cutting the bytes of the old 192 px renders.
LARGE_MAX = (128, 128)
# Inline badge/footer icons render at 16 CSS px; keep enough pixels for HiDPI
# displays (Lighthouse expects >= 2x the displayed size).
INLINE_ICON_MAX = (64, 64)
# Explicit AVIF quality. Pillow defaults to ~75; at these small display sizes
# 60 is visually indistinguishable and meaningfully smaller.
AVIF_QUALITY = 60

with open('gazette.toml', 'rb') as f:
	content = f.read()
	config_data = tomllib.loads(content.decode('utf-8'))
	print(f'Found {len(config_data["feeds"]["feedlist"])} feeds in config.')

	# Optional domain arguments limit the run to specific sources, so adding one
	# feed does not rewrite every favicon (and produce a noisy diff).
	only = set(sys.argv[1:])
	for feed in config_data['feeds']['feedlist']:
		domain = feed['domain']
		if only and domain not in only:
			continue
		small_path = os.path.join('static', 'favicons', f'{domain}.avif')
		large_path = os.path.join('static', 'favicons', f'{domain}-large.avif')
		os.makedirs(os.path.dirname(small_path), exist_ok=True)
		try:
			response = requests.get(feed['image'], timeout=10, headers=headers)
			response.raise_for_status()
			raw = response.content
			content_type = response.headers.get('Content-Type', '').lower()
			is_svg = 'svg' in content_type or feed['image'].lower().split('?')[0].endswith('.svg')
			if is_svg:
				# SVG is vector — render at each target size for crisp output
				png_small = cairosvg.svg2png(bytestring=raw, output_width=SMALL_SIZE[0], output_height=SMALL_SIZE[1])
				Image.open(BytesIO(png_small)).save(small_path, 'AVIF', quality=AVIF_QUALITY)
				png_large = cairosvg.svg2png(bytestring=raw, output_width=LARGE_MAX[0], output_height=LARGE_MAX[1])
				Image.open(BytesIO(png_large)).save(large_path, 'AVIF', quality=AVIF_QUALITY)
			else:
				# Raster: 32×32 for posts; thumbnail preserves aspect and never upscales for sources
				Image.open(BytesIO(raw)).resize(SMALL_SIZE).save(small_path, 'AVIF', quality=AVIF_QUALITY)
				img_large = Image.open(BytesIO(raw))
				img_large.thumbnail(LARGE_MAX, Image.Resampling.LANCZOS)
				img_large.save(large_path, 'AVIF', quality=AVIF_QUALITY)
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

# Convert navbar logo to a properly sized AVIF
navbar_src = os.path.join('static', 'icons', 'favicon-96x96.png')
navbar_dst = os.path.join('static', 'icons', 'favicon-96x96.avif')
try:
	Image.open(navbar_src).save(navbar_dst, 'AVIF', quality=AVIF_QUALITY)
	print(f'Converted {navbar_src} to AVIF')
except Exception as e:
	print(f'Failed to convert navbar logo: {e}')

for root, dirs, files in os.walk('static/img'):
	for file in files:
		file_path = os.path.join(root, file)
		if file.endswith(('.png', '.webp', '.jpg', '.jpeg')):
			# Open file and convert to AVIF
			image_path = file_path.rsplit('.', 1)[0] + '.avif'
			with open(file_path, 'rb') as f:
				file_content = f.read()
				img = Image.open(BytesIO(file_content))
				img.thumbnail(INLINE_ICON_MAX, Image.Resampling.LANCZOS)
				img.save(image_path, 'AVIF', quality=AVIF_QUALITY)

# Regenerate the per-logo dark/light theme rules from the favicons just built.
subprocess.run([sys.executable, os.path.join('build_tools', 'favicon_theme.py')], check=True)
