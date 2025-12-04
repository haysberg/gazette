import os

import requests

css_path = os.path.join(
	'static',
	'css',
	'daisy.min.css',
)
daisy_css = requests.get('https://cdn.jsdelivr.net/npm/daisyui@5')
with open(css_path, 'w') as f:
	f.write(daisy_css.text)

js_path = os.path.join(
	'static',
	'js',
	'daisy.min.js',
)
daisy_js = requests.get('https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4')
with open(js_path, 'w') as f:
	f.write(daisy_js.text)
