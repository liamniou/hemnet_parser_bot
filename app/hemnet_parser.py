import json
import logging as log
import os
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from mongodb_functions import find_in_collection, insert_to_collection
from telegraph_functions import upload_image_to_telegraph, create_telegraph_page
from with_browser_v2 import open_page_find_images


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))


def find_cell_value(soup, label_text, value_cell_class, rows_class="div.property-attributes-table__row"):
    items = soup.select(rows_class)
    for item in items:
        if label_text in item.text:
            return item.select_one(value_cell_class).text


def find_links_in_hemnet_search_results():
    links = []
    page_url = os.getenv(
        "PAGE_URL",
        "https://www.hemnet.se/bostader?location_ids%5B%5D=18031&"
        "item_types%5B%5D=bostadsratt"
        "&rooms_min=2&living_area_min=50&living_area_max=75&price_min=4000000"
        "&price_max=6500000&new_construction=exclude&published_since=1d",
    )
    with httpx.Client() as client:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"}
        r = client.get(page_url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        results = soup.find_all("li", class_="normal-results__hit js-normal-list-item")
        for item in results:
            if item.get("data-gtm-item-page"):
                links.append(item.find("a", class_="js-listing-card-link listing-card")["href"])
    return links


def parse_hemnet_page(page_url):
    @dataclass
    class ParsedValues:
        link: str
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
            self.avgift = self.avgift.replace("\xa0", " ") if self.avgift else "N/a"
            self.price = self.price.replace("\xa0", " ") if self.price else "N/a"
            self.sq_m_price = self.sq_m_price.replace("\xa0", " ") if self.sq_m_price else "N/a"
            self.balcony = self.balcony.strip() if self.balcony else "N/a"
            self.level = self.level.strip() if self.level else "N/a"
            self.area = self.area.strip() if self.area else "N/a"
            self.year = self.year.strip() if self.year else "N/a"
            self.rooms_n = self.rooms_n.replace(" rum", "") if self.rooms_n else "N/a"

    with httpx.Client() as client:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"}
        r = client.get(page_url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")

        obj = ParsedValues(
            page_url,
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


def send_tg_message(chat_id, message, reply_id=None):
    with httpx.Client() as client:
        data_dict = {"chat_id": chat_id, "text": message}
        if reply_id:
            data_dict = {**data_dict, **{"reply_to_message_id": reply_id, "allow_sending_without_reply": False}}
        r = client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=data_dict)
        log.warning(r.json())
        return r.json()


def send_tg_location(chat_id, address, reply_id):
    try:
        with httpx.Client() as client:
            maps_api = (
                f"https://nominatim.openstreetmap.org/"
                f"search?q=Sweden+Stockholm+{address}"
                f"&format=json&polygon=1&addressdetails=1"
            )
            maps_r = json.load(client.get(maps_api))
            lat = maps_r[0]["lat"]
            lon = maps_r[0]["lon"]
            with httpx.Client() as client:
                data_dict = {
                    "chat_id": chat_id,
                    "latitude": lat,
                    "longitude": lon,
                    "reply_to_message_id": reply_id,
                    "allow_sending_without_reply": True,
                }
                r = client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendLocation", data=data_dict)
                log.warning(r.text)
    except:
        log.error("Can't determine location")


def create_html_from_parsed_page(parsed_page):
    title = f"{parsed_page.title}"
    telegraph_imgs = ""
    for image_link in parsed_page.property_imgs:
        telegraph_imgs += f"<img src='{upload_image_to_telegraph(image_link)}'><br>"

    html_content = f"""
<h4>{parsed_page.price}</h4>
<p>{parsed_page.link}</p>
<p><i>{parsed_page.address_area}</i></p>
<p>{parsed_page.rooms_n} rooms, {parsed_page.area}, Balcony: {parsed_page.balcony}, {parsed_page.level}, {parsed_page.year} year</p>
<p>{parsed_page.avgift} - {parsed_page.sq_m_price}</p>
{telegraph_imgs}"""
    return title, html_content


def main():
    send_tg_message(ADMIN_CHAT_ID, "Hemnet parser started")
    links = find_links_in_hemnet_search_results()
    for link in links:
        log.warning(link)
        if not find_in_collection({"href": link}):
            log.warning(f"{link} doesn't exist in DB, processing...")
            parsed_page = parse_hemnet_page(link)
            title, html_content = create_html_from_parsed_page(parsed_page)
            telegraph_page = create_telegraph_page(title, html_content)
            if telegraph_page:
                log.warning(telegraph_page)
                m_id = send_tg_message(CHAT_ID, telegraph_page["url"])["result"]["message_id"]
                insert_to_collection(
                    {"href": link, "telegraph_link": telegraph_page["url"], "message_id": m_id, "sold_price": None}
                )
                send_tg_location(CHAT_ID, parsed_page.title.split(",")[0].replace(" ", "+"), m_id)


if __name__ == "__main__":
    main()
