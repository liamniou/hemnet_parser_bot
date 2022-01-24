import json
import logging as log
import os
import re
import httpx
import telebot
from bs4 import BeautifulSoup
from with_browser import open_page_find_images
from telebot import types
from time import sleep


bot = telebot.TeleBot(
    os.getenv("TELEGRAM_BOT_TOKEN"),
    threaded=False,
    parse_mode="MARKDOWN",
)
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS").split(",")]
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
CHAT_ID = int(os.getenv("CHAT_ID"))


def parse_hemnet_page(page_url):
    obj = {
        "title": None,
        "address_area": None,
        "rooms_n": None,
        "area": None,
        "balcony": None,
        "level": None,
        "year": None,
        "price": None,
        "avgift": None,
        "sq_m_price": None,
        "property_imgs": [],
    }

    with httpx.Client() as client:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"}
        r = client.get(page_url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")

        obj["title"] = soup.select("h1.qa-property-heading")[0].text
        obj["price"] = soup.select("p.property-info__price.qa-property-price")[0].text.replace("\xa0", " ")
        obj["address_area"] = soup.select("span.property-address__area")[0].text
        obj["rooms_n"] = soup.select("dd.property-attributes-table__value")[2].text.replace(" rum", "")
        obj["area"] = soup.select("dd.property-attributes-table__value")[3].text
        obj["balcony"] = soup.select("dd.property-attributes-table__value")[4].text.strip()
        obj["level"] = soup.select("dd.property-attributes-table__value")[5].text.strip()
        obj["year"] = soup.select("dd.property-attributes-table__value")[6].text.strip()
        obj["avgift"] = soup.select("dd.property-attributes-table__value")[8].text.replace("\xa0", " ")
        obj["sq_m_price"] = soup.select("dd.property-attributes-table__value")[9].text.replace("\xa0", " ")
        obj["property_imgs"] = open_page_find_images(page_url)

    return obj


def split_list_to_chunks(input_list, size):
    for i in range(0, len(input_list), size):
        yield input_list[i:i + size]


def send_text_message(parsing_result, chat_id):
    message = f"""
*{parsing_result['title']} {parsing_result['price']}*
{parsing_result['address_area']}
{parsing_result['rooms_n']}, {parsing_result['area']}, Balcony: {parsing_result['balcony']}, {parsing_result['level']}, {parsing_result['year']}
{parsing_result['avgift']} - {parsing_result['sq_m_price']}
"""
    bot.send_message(chat_id, message)


def send_location(parsing_result, chat_id):
    try:
        with httpx.Client() as client:
            maps_api = (
                f"https://nominatim.openstreetmap.org/"
                f"search?q=Sweden+Stockholm+{parsing_result['title'].split(',')[0].replace(' ', '+')}"
                f"&format=json&polygon=1&addressdetails=1"
            )
            maps_r = json.load(client.get(maps_api))
            lat = maps_r[0]["lat"]
            lon = maps_r[0]["lon"]
            bot.send_location(chat_id, lat, lon)
    except:
        log.error("Can't determine location")


def send_media_message(parsing_result, chat_id):
    split_media_list = split_list_to_chunks(parsing_result["property_imgs"], 9)
    delay = 30
    for list_part in split_media_list:
        medias = []
        for image in list_part:
            image_file_name = image.split('/')[-1]
            local_file_path = f"/tmp/{image_file_name}"
            with open(local_file_path, 'wb') as f:
                with httpx.stream('GET', image) as r:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            photo = open(local_file_path, 'rb')
            medias.append(types.InputMediaPhoto(photo, image_file_name))
        try:
            bot.send_media_group(chat_id, medias, timeout=30)
            sleep(delay)
            delay += 30
        except Exception as e:
            log.error(e)


@bot.message_handler(commands=["start"])
def send_welcome(message):
    log.info(f"{message.chat.id}: {message.text}")
    if message.chat.id in AUTHORIZED_USERS:
        bot.reply_to(message, "Hi there, I am hemnet.se parser bot.")
    else:
        bot.reply_to(message, "Sorry, I'm a private bot.")


@bot.channel_post_handler(func=lambda m: m.text is not None and "hemnet.se" in m.text)
def parse_hemnet_link(message):
    if message.chat.id == CHAT_ID:
        result = bot.send_message(message.chat.id, "Processing your link, please wait...")
        page_url = re.search("(?P<url>https?://[^\s]+)", message.text).group("url")
        log.info(f"{message.chat.id}: {message.text}; Extracted URL: {page_url}")
        parsing_result = parse_hemnet_page(page_url)
        log.info(parsing_result)
        send_text_message(parsing_result, message.chat.id)
        send_location(parsing_result, message.chat.id)
        send_media_message(parsing_result, message.chat.id)
        bot.delete_message(message.chat.id, result.message_id)
    else:
        bot.send_message(message.chat.id, "Sorry, this is a private bot")


def main():
    bot.send_message(ADMIN_CHAT_ID, "Bot has been started")
    bot.polling()


if __name__ == "__main__":
    main()
