# Replaces the original file with the minified version
import gzip
import os

from csscompressor import compress
from jsmin import jsmin

with open('static/js/index.js') as js_file:
	minified = jsmin(js_file.read())
	with open('static/js/index.min.js', 'w') as minified_js:
		minified_js.write(minified)

with open('static/css/style.css', 'r') as css_file:
	compressed_css: str = compress(css_file.read())
	with open('static/css/style.min.css', 'w') as minified_css_file:
		_ = minified_css_file.write(compressed_css)

for root, dirs, files in os.walk('static'):
	for file in files:
		file_path = os.path.join(root, file)
		if not file.endswith('.gz'):
			with open(file_path, 'rb') as f_in:
				data = f_in.read()
				# gzip
				gz_path = file_path + '.gz'
				with open(gz_path, 'wb') as f_out:
					compressed: bytes = gzip.compress(data)
					_ = f_out.write(compressed)
