# Replaces the original file with the minified version
import gzip
import hashlib
import os
import time

import brotli

from csscompressor import compress
from jsmin import jsmin

with open('static/js/index.js') as js_file:
	minified = jsmin(js_file.read())
	with open('static/js/index.min.js', 'w') as minified_js:
		minified_js.write(minified)

with open('static/sw.js') as sw_file:
	sw_content = sw_file.read()
	# Inject a unique cache name per build to bust stale service worker caches
	cache_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
	sw_content = sw_content.replace('CACHE_PLACEHOLDER', f'gazette-{cache_hash}')
	minified_sw = jsmin(sw_content)
	with open('static/sw.js', 'w') as sw_out:
		sw_out.write(minified_sw)

with open('static/css/style.css', 'r') as css_file:
	compressed_css: str = compress(css_file.read())
	with open('static/css/style.min.css', 'w') as minified_css_file:
		_ = minified_css_file.write(compressed_css)
	# Generate inline style template for embedding in <head>
	with open('templates/inline_style.html', 'w') as inline_file:
		inline_file.write(f'<style>{compressed_css}</style>')

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
