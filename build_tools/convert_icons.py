import os

from PIL import Image

icons_dir = os.path.join('static', 'icons')

# App/PWA icons are shown larger than the inline badges, so keep a little more
# fidelity than the badge encoder.
AVIF_QUALITY = 70

for filename in os.listdir(icons_dir):
	if not filename.endswith('.png'):
		continue
	png_path = os.path.join(icons_dir, filename)
	avif_path = os.path.join(icons_dir, filename.removesuffix('.png') + '.avif')
	try:
		Image.open(png_path).save(avif_path, 'AVIF', quality=AVIF_QUALITY)
		print(f'{filename} -> {os.path.basename(avif_path)}')
	except Exception as e:
		print(f'Failed to convert {filename}: {e}')
