import json
import logging as log
import os
import re
import httpx
import telebot
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
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


def find_cell_value(
    soup, label_text, value_cell_class, rows_class="div.property-attributes-table__row"
):
    items = soup.select(rows_class)
    for item in items:
        if label_text in item.text:
            return item.select_one(value_cell_class).text


def parse_hemnet_page(page_url):
    @dataclass
    class ParsedValues:
        title: str
        price: str
        address_area: str
        rooms_n: str
        area: str
        balcony: str
        level: str
        year: str
        avgift: str
        sq_m_price: str
        property_imgs: list = field(default_factory=list)

        def __post_init__(self):
            self.avgift = self.avgift.replace("\xa0", " ") if self.avgift else 'N/a'
            self.price = self.price.replace("\xa0", " ") if self.price else 'N/a'
            self.sq_m_price = self.sq_m_price.replace("\xa0", " ") if self.sq_m_price else 'N/a'
            self.balcony = self.balcony.strip() if self.balcony else 'N/a'
            self.level = self.level.strip() if self.level else 'N/a'
            self.area = self.area.strip() if self.area else 'N/a'
            self.year = self.year.strip() if self.year else 'N/a'
            self.rooms_n = self.price.replace(" rum", "") if self.rooms_n else 'N/a'

    with httpx.Client() as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"
        }
        r = client.get(page_url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")

        obj = ParsedValues(
            soup.select_one("h1.qa-property-heading").text,
            find_cell_value(
                soup,
                "",
                "p.property-info__price.qa-property-price",
                "div.property-info__price-container",
            ),
            soup.select_one("span.property-address__area").text,
            find_cell_value(soup, "Antal rum", "dd.property-attributes-table__value"),
            find_cell_value(soup, "Boarea", "dd.property-attributes-table__value"),
            find_cell_value(soup, "Balkong", "dd.property-attributes-table__value"),
            find_cell_value(soup, "Våning", "dd.property-attributes-table__value"),
            find_cell_value(soup, "Byggår", "dd.property-attributes-table__value"),
            find_cell_value(soup, "Avgift", "dd.property-attributes-table__value"),
            find_cell_value(soup, "Pris/m²", "dd.property-attributes-table__value"),
            open_page_find_images(page_url),
        )

    return obj


def split_list_to_chunks(input_list, size):
    for i in range(0, len(input_list), size):
        yield input_list[i : i + size]


def send_text_message(parsed_result, chat_id):
    message = f"""
*{parsed_result.title} {parsed_result.price}*
{parsed_result.address_area}
{parsed_result.rooms_n}, {parsed_result.area}, Balcony: {parsed_result.balcony}, {parsed_result.level}, {parsed_result.year}
{parsed_result.avgift} - {parsed_result.sq_m_price}
"""
    bot.send_message(chat_id, message)


def send_location(parsed_result, chat_id):
    try:
        with httpx.Client() as client:
            maps_api = (
                f"https://nominatim.openstreetmap.org/"
                f"search?q=Sweden+Stockholm+{parsed_result.title.split(',')[0].replace(' ', '+')}"
                f"&format=json&polygon=1&addressdetails=1"
            )
            maps_r = json.load(client.get(maps_api))
            lat = maps_r[0]["lat"]
            lon = maps_r[0]["lon"]
            bot.send_location(chat_id, lat, lon)
    except:
        log.error("Can't determine location")


def send_media_message(parsed_result, chat_id):
    split_media_list = split_list_to_chunks(parsed_result.property_imgs, 9)
    delay = 30
    for list_part in split_media_list:
        medias = []
        for image in list_part:
            image_file_name = image.split("/")[-1]
            local_file_path = f"/tmp/{image_file_name}"
            with open(local_file_path, "wb") as f:
                with httpx.stream("GET", image) as r:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            photo = open(local_file_path, "rb")
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
        result = bot.send_message(
            message.chat.id, "Processing your link, please wait..."
        )
        page_url = re.search("(?P<url>https?://[^\s]+)", message.text).group("url")
        log.info(f"{message.chat.id}: {message.text}; Extracted URL: {page_url}")
        parsed_result = parse_hemnet_page(page_url)
        log.info(parsed_result)
        send_text_message(parsed_result, message.chat.id)
        send_location(parsed_result, message.chat.id)
        send_media_message(parsed_result, message.chat.id)
        bot.delete_message(message.chat.id, result.message_id)
    else:
        bot.send_message(message.chat.id, "Sorry, this is a private bot")


def main():
    bot.send_message(ADMIN_CHAT_ID, "Bot has been started")
    bot.polling()


if __name__ == "__main__":
    main()
