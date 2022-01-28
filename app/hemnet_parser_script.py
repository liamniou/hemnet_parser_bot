import os
import httpx
from bs4 import BeautifulSoup


def hemnet_search_results_to_tg_msg():
    messages = []
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
        i = 1
        for item in results:
            if item.get("data-gtm-item-page"):
                title = (
                    item.find("h2", class_="listing-card__street-address qa-listing-title").text.strip().split(",")[0]
                )
                district = item.find("span", class_="listing-card__location-name").text.strip().split(",")[0]
                attributes = item.find_all("div", class_="listing-card__attribute listing-card__attribute--primary")
                price = attributes[0].text.strip()
                area = " ".join(attributes[1].text.split())
                rooms = attributes[2].text.strip()
                link = item.find("a", class_="js-listing-card-link listing-card")
                messages.append(f"{i} [*{title}* {district}]({link['href']}) {price}, {area}, {rooms}")
                i += 1
    return "\n".join(messages).replace('-', '\\-').replace('+', '\\+')


def send_telegram_message(message_text):
    with httpx.Client() as client:
        data_dict = {
            "chat_id": os.getenv("CHAT_ID"),
            "text": message_text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        r = client.post(
            f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
            data=data_dict
        )
        print(r.text)


def parse_ads_and_send_to_tg():
    message = hemnet_search_results_to_tg_msg()
    send_telegram_message(message)


parse_ads_and_send_to_tg()
