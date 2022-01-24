import logging as log
import os
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from time import sleep


chrome_options = Options()
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox") # linux only
chrome_options.add_argument("--headless")
ACTION_PAUSE = int(os.getenv("ACTION_PAUSE", 3))


def open_page_find_images(url):
    try:
        image_links = []
        browser = webdriver.Chrome(options=chrome_options)
        browser.get(url)
        sleep(ACTION_PAUSE)
        cookies_button = browser.find_element_by_css_selector(
            "body > div.ReactModalPortal > div > div > div > div > div > "
            "div:nth-child(2) > div.consent__buttons > div:nth-child(2) > button")
        cookies_button.click()

        gallery_button = browser.find_element_by_css_selector(
            "body > div.listing-container.qa-listing-container > "
            "div > div.listing__property-info.qa-property-info > "
            "div.property-info__container > div.property-gallery > "
            "div.property-gallery__image-container > div > "
            "div.property-carousel.js-carousel-container.qa-carousel > div > "
            "div > div.gallery-carousel > div > div > div > div > ul > "
            "li.slide.selected > button")
        gallery_button.click()
        sleep(ACTION_PAUSE)

        # Scroll to last div to get all images loaded
        data_index_divs = browser.find_elements_by_xpath("//div[@data-index]")
        for div in data_index_divs:
            log.info(f"Checking div #{div.get_attribute('data-index')}")
            browser.execute_script("arguments[0].scrollIntoView();", div)
            sleep(0.5)

        loaded_images = browser.find_elements_by_xpath("//img[@class='all-images__image all-images__image--loaded']")
        for image in loaded_images:
            src = image.get_attribute("src")
            log.info(f"Found image {src}")
            image_links.append(src)

    finally:
        browser.quit()
        return image_links
