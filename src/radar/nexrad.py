import os
import json
import urllib.request

FILE_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.dirname(FILE_DIR)
BLOB_DIR = os.path.join(BASE_DIR, "blob")
if not os.path.exists(BLOB_DIR):
    os.mkdir(BLOB_DIR)

nexrad_db = os.path.join(BLOB_DIR, "nexrad-locations.json")
nexrad = {}


def get_nexrad_location(site):
    global nexrad
    if len(nexrad) == 0:
        if os.path.exists(nexrad_db):
            with open(nexrad_db) as fid:
                nexrad = json.load(fid)
        else:
            url = "https://raw.githubusercontent.com/ouradar/radar-data/master/blob/nexrad-locations.json"
            print(f"Retrieving {url} ...")
            response = urllib.request.urlopen(url)
            if response.status == 200:
                nexrad = json.loads(response.read())
                with open(nexrad_db, "w") as fid:
                    json.dump(nexrad, fid)
    key = site.upper()
    if key in nexrad:
        return nexrad[key]
    return None
