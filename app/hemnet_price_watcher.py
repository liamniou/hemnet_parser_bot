import httpx
from bs4 import BeautifulSoup
from mongodb_functions import *
from hemnet_parser import send_tg_message


CHAT_ID = int(os.getenv("CHAT_ID"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))


def find_sold_items():
    items_with_null_price = find_all_in_collection({"sold_price": None})
    for item in items_with_null_price:
        link = item["href"]
        with httpx.Client() as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"}
            r = client.get(link, headers=headers)
            soup = BeautifulSoup(r.text, "html.parser")
            result = soup.find(
                "a", class_="hcl-button hcl-button--primary hcl-button--full-width qa-removed-listing-button"
            )
            if result:
                log.warning(f"{link} is sold, checking the final price...")
                r = client.get(result["href"], headers=headers)
                soup = BeautifulSoup(r.text, "html.parser")
                final_price = soup.find("span", class_="sold-property__price-value").text
                dd_diff = soup.find_all("dd", class_="sold-property__attribute-value")
                for dd in dd_diff:
                    if "%" in dd.text:
                        diff = dd.text.strip()
                send_tg_message(CHAT_ID, f"Sold for {final_price} ({diff})", item["message_id"])
                update_in_collection({"href": link}, {"$set": {"sold_price": final_price}})


send_tg_message(ADMIN_CHAT_ID, f"Hemnet price watcher started")
find_sold_items()
