from io import BytesIO
import os
import tomllib
import cairosvg
import requests
from PIL import Image

with open("config.toml", "rb") as f:
    content = f.read()
    config_data = tomllib.loads(content.decode("utf-8"))
    for feed in config_data["feeds"]["feedlist"]:
        retries = 3
        for attempt in range(retries):
            try:
                image_path = os.path.join(
                    "static",
                    "favicons",
                    f"{feed['image'].split('/')[2].removeprefix('www.')}.webp",
                )
                os.makedirs(os.path.dirname(image_path), exist_ok=True)

                response = requests.get(feed["image"], timeout=10, verify=False)
                response.raise_for_status()

                img_data = BytesIO(response.content)
                if feed["image"].endswith(".svg"):
                    png_data = BytesIO()
                    cairosvg.svg2png(bytestring=img_data.getvalue(), write_to=png_data)
                    img_data = png_data

                Image.open(img_data).resize((32, 32), Image.LANCZOS).save(
                    image_path, "WEBP"
                )
                break  # Success, exit retry loop
            except Exception as e:
                if attempt == retries - 1:
                    print(f"Failed to process favicon for {feed['link']}: {e}")
                else:
                    continue
