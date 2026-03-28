import os

from PIL import Image

icons_dir = os.path.join('static', 'icons')

for filename in os.listdir(icons_dir):
	if not filename.endswith('.png'):
		continue
	png_path = os.path.join(icons_dir, filename)
	avif_path = os.path.join(icons_dir, filename.removesuffix('.png') + '.avif')
	if os.path.exists(avif_path):
		continue
	try:
		Image.open(png_path).save(avif_path, 'AVIF')
		print(f'{filename} -> {os.path.basename(avif_path)}')
	except Exception as e:
		print(f'Failed to convert {filename}: {e}')
