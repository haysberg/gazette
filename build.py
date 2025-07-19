from io import BytesIO
import os
import gzip
import tomllib
import cairosvg
from jsmin import jsmin
import requests
from PIL import Image

with open("config.toml", "rb") as f:
    content = f.read()
    config_data = tomllib.loads(content.decode("utf-8"))
    for feed in config_data["feeds"]["feedlist"]:
        image_path = os.path.join(
            "static",
            "favicons",
            f"{feed['link'].split('/')[2].removeprefix('www.')}.webp",
        )
        os.makedirs(os.path.dirname(image_path), exist_ok=True)

        response = requests.get(feed["image"], timeout=10, verify=False)
        response.raise_for_status()

        img_data = BytesIO(response.content)
        if feed["image"].endswith(".svg"):
            png_data = BytesIO()
            cairosvg.svg2png(bytestring=img_data.getvalue(), write_to=png_data)
            img_data = png_data

        Image.open(img_data).resize((32, 32), Image.LANCZOS).save(image_path, "WEBP")

# Replace the original file with the minified version
with open("static/index.js") as js_file:
    minified = jsmin(js_file.read())
    with open("static/index.min.js", "w") as minified_file:
        minified_file.write(minified)

# Compress style.css using csscompressor
from csscompressor import compress

with open("static/style.css", "r") as css_file:
    compressed_css = compress(css_file.read())
    with open("static/style.min.css", "w") as minified_css_file:
        minified_css_file.write(compressed_css)

for root, dirs, files in os.walk("static"):
    for file in files:
        file_path = os.path.join(root, file)
        if not file.endswith((".gz", ".br", ".zst")):  # Skip already compressed files
            with open(file_path, "rb") as f_in:
                data = f_in.read()
            gz_path = file_path + ".gz"
            with open(gz_path, "wb") as f_out:
                compressed = gzip.compress(data)
                f_out.write(compressed)
