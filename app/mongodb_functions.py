import logging as log
import os
from pymongo import MongoClient

client = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
hemnet_db = client.hemnet.processed_links


def find_all_in_collection(obj):
    return hemnet_db.find(obj)


def find_in_collection(obj):
    return hemnet_db.find_one(obj)


def update_in_collection(obj, new_value):
    res = hemnet_db.update_one(obj, new_value)
    log.warning(res)


def insert_to_collection(obj):
    res = find_in_collection(obj)
    if res:
        log.warning("The link has already been processed before")
    else:
        hemnet_db.insert_one(obj)
