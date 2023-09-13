import logging as log
from playwright.sync_api import sync_playwright


def open_page_find_images(url):
    image_links = []
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True, slow_mo=1000)
            page = browser.new_page()
            page.goto(url)

            # Accept cookies
            accept_cookies = page.get_by_role("button", name="Acceptera alla")
            accept_cookies.click()

            # Open gallery
            gallery_button = page.locator(
                "body > div.listing-container.qa-listing-container > div > div.listing__property-info.qa-property-info > div.property-info__container > div.property-gallery > div.property-gallery__image-container > div > div.property-carousel.js-carousel-container.qa-carousel > div > div > div.property-gallery__button-container > button"
            )
            gallery_button.click()

            # Scroll to last div to get all images loaded
            data_index_divs = page.locator("//div[@data-index]")
            count = data_index_divs.count()

            for i in range(count):
                div = data_index_divs.nth(i)
                div.scroll_into_view_if_needed()

            # Loop through all loaded images
            loaded_images = page.locator(
                "//img[@class='all-images__image all-images__image--loaded']"
            )
            count = loaded_images.count()

            for i in range(count):
                image = loaded_images.nth(i)
                src = image.get_attribute("src")
                log.info(f"Found image {src}")
                image_links.append(src)
    finally:
        return image_links


print(open_page_find_images("https://www.hemnet.se/bostad/lagenhet-3,5rum-djursholm-danderyds-kommun-viktor-rydbergs-vag-13a-19972965"))