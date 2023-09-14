import httpx
import logging as log
import os
from telegraph import Telegraph


telegraph = Telegraph(access_token=os.getenv("TELEGRAPH_TOKEN", ""))


def create_account(short_name):
    r = telegraph.create_account(short_name=short_name)
    return r


def upload_image_to_telegraph(image_url):
    try:
        image_file_name = image_url.split("/")[-1]
        local_file_path = f"/tmp/{image_file_name}"
        extension = local_file_path.split(",")[-1]
        with open(local_file_path, "wb") as f:
            with httpx.stream("GET", image_url) as r:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        with open(local_file_path, "rb") as f:
            r = httpx.post("https://telegra.ph/upload", files={"file": ("file", f, f"image/{extension}")})
            return r.json()[0]["src"]
    except Exception as e:
        log.error(e)
        return ""



def create_telegraph_page(title, html_content):
    r = telegraph.create_page(title, html_content=html_content)
    return r
