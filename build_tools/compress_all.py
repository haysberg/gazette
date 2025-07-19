# Replace the original file with the minified version
import gzip
import os
from csscompressor import compress
from jsmin import jsmin
import brotli
import zstandard as zstd


with open("static/index.js") as js_file:
    minified = jsmin(js_file.read())
    with open("static/index.min.js", "w") as minified_file:
        minified_file.write(minified)

with open("static/style.css", "r") as css_file:
    compressed_css = compress(css_file.read())
    with open("static/style.min.css", "w") as minified_css_file:
        minified_css_file.write(compressed_css)

for root, dirs, files in os.walk("static"):
    for file in files:
        file_path = os.path.join(root, file)
        if not file.endswith((".gz", ".br", ".zst")):
            with open(file_path, "rb") as f_in:
                data = f_in.read()
                # gzip
                gz_path = file_path + ".gz"
                with open(gz_path, "wb") as f_out:
                    compressed = gzip.compress(data)
                    f_out.write(compressed)
                # brotli
                try:
                    br_path = file_path + ".br"
                    with open(br_path, "wb") as f_out:
                        compressed = brotli.compress(data)
                        f_out.write(compressed)
                except Exception:
                    pass
                # zstandard
                try:
                    zst_path = file_path + ".zst"
                    with open(zst_path, "wb") as f_out:
                        cctx = zstd.ZstdCompressor()
                        compressed = cctx.compress(data)
                        f_out.write(compressed)
                except Exception:
                    pass