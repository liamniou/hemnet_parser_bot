import httpx
import time
from bs4 import BeautifulSoup
from mongodb_functions import *
from hemnet_parser import send_tg_message


CHAT_ID = int(os.getenv("CHAT_ID"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))


def find_sold_items():
    items_with_null_price = find_all_in_collection({"sold_price": None})
    for item in items_with_null_price:
        link = item["href"]
        # Link with no final price button
        # link = "https://www.hemnet.se/bostad/lagenhet-4rum-djursholm-danderyds-kommun-ynglingavagen-11-12482217"
        # Link with final price button
        # link = "https://www.hemnet.se/bostad/lagenhet-2rum-lilla-essingen-kungsholmen-stockholms-kommun-disponentgatan-6-18219635"
        with httpx.Client() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"
            }
            r = client.get(link, headers=headers)
            soup = BeautifulSoup(r.text, "html.parser")
            removed_listing_div = soup.find(
                "div", class_="removed-listing qa-removed-listing"
            )
            if removed_listing_div:
                log.warning(f"{link} is sold, checking the final price...")
                final_price = "n/a"
                try:
                    final_price_button = soup.find(
                        "a",
                        class_="hcl-button hcl-button--primary hcl-button--full-width qa-removed-listing-button",
                    )
                    sold_page = client.get(final_price_button["href"], headers=headers)
                    soup = BeautifulSoup(sold_page.text, "html.parser")
                    final_price = soup.find(
                        "span", class_="sold-property__price-value"
                    ).text
                    dd_diff = soup.find_all(
                        "dd", class_="sold-property__attribute-value"
                    )
                    for dd in dd_diff:
                        if "%" in dd.text:
                            final_price += f" ({dd.text.strip()})"
                except Exception as e:
                    log.error(f"{e}: Can't find the final price for {link}")
                finally:
                    log.warning(f"Sold for {final_price}")
                    send_tg_message(CHAT_ID, f"Sold for {final_price}", item["message_id"])
                    update_in_collection({"href": link}, {"$set": {"sold_price": final_price}})
                    # Wait for 5 sec after sending the Telegram message to avoid API rate limiting
                    time.sleep(5)


send_tg_message(ADMIN_CHAT_ID, f"Hemnet price watcher started")
find_sold_items()
