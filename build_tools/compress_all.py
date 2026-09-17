# Replaces the original file with the minified version
import gzip
import hashlib
import os
import re

import brotli

from csscompressor import compress
from jsmin import jsmin

with open('static/js/index.js') as js_file:
	minified = jsmin(js_file.read())
	with open('static/js/index.min.js', 'w') as minified_js:
		minified_js.write(minified)

with open('src/sw.js') as sw_file:
	sw_content = sw_file.read()
	# Inject a content-based cache name so the SW busts cache when assets change
	content_to_hash = b''
	for asset_path in ['static/css/daisy.min.css', 'static/js/index.min.js']:
		with open(asset_path, 'rb') as af:
			content_to_hash += af.read()
	cache_hash = hashlib.md5(content_to_hash).hexdigest()[:8]
	# The source keeps a stable CACHE_PLACEHOLDER; every build rewrites the
	# generated copy from scratch, so there is no stale-name problem here.
	sw_content = re.sub(r'CACHE_PLACEHOLDER', f'gazette-{cache_hash}', sw_content)
	minified_sw = jsmin(sw_content)
	with open('static/sw.js', 'w') as sw_out:
		sw_out.write(minified_sw)

with open('static/css/style.css', 'r') as css_file:
	compressed_css: str = compress(css_file.read())
	with open('static/css/style.min.css', 'w') as minified_css_file:
		_ = minified_css_file.write(compressed_css)

for root, dirs, files in os.walk('static'):
	for file in files:
		file_path = os.path.join(root, file)
		if file.endswith(('.gz', '.br')):
			continue
		with open(file_path, 'rb') as f_in:
			data = f_in.read()
		with open(file_path + '.gz', 'wb') as f_out:
			f_out.write(gzip.compress(data))
		with open(file_path + '.br', 'wb') as f_out:
			f_out.write(brotli.compress(data, quality=11))
