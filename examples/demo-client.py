import os
import sys
import glob
import time
import random
import logging
import datetime
import threading

srcDir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
if os.path.exists(srcDir):
    print(f"Inserting {srcDir} into sys.path")
    sys.path.insert(0, srcDir)

import radar

logger = logging.getLogger("demo-client")
formatter = logging.Formatter(radar.cosmetics.log_format)
fileHandler = logging.FileHandler(os.path.expanduser("~/logs/demo-client.log"))
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)
streamHandler.setLevel(logging.INFO)
logger.addHandler(streamHandler)
logger.setLevel(logging.INFO)

SIMULATE_DELAY = False


def request(client, file):
    logger.info(f"Req: {file} ...")
    data = client.get(file)
    if data is None:
        logger.info(f"Ign: {file} ...")
        return None
    timestamp = datetime.datetime.fromtimestamp(data["time"], tz=datetime.timezone.utc)
    timeString = timestamp.strftime(r"%Y%m%d-%H%M%S")
    basename = os.path.basename(file)
    match = radar.re_datetime_s.search(basename)
    target = match[0].replace("_", "-").replace(".", "-") if match else None
    mark = (
        radar.cosmetics.check
        if target == timeString
        else radar.cosmetics.ignore if target[:8] == timeString[:8] else radar.cosmetics.cross
    )
    logger.info(f"Out: {basename} / {timeString} {mark}")
    return data


###

logger.info("Starting ...")

client = radar.product.Client(count=6, logger=logger)

# Replace with where the data is stored
# if os.path.exist("/mnt/data/PX1000"):
#     files = sorted(glob.glob("/mnt/data/PX1000/2024/20240820/_original/*xz"))
# elif os.path.exist("/Volumes/Data/PX1000"):
#     files = sorted(glob.glob("/Volumes/Data/PX1000/2024/20240820/_original/*xz"))

files = [
    "~/Downloads/data/read-test/PX-20240529-150246-E4.0.tar.xz",  # WDSS-II collections in tar.xz
    "~/Downloads/data/read-test/PX-20240529-150246-E4.0-Z.nc",  # WDSS-II, auto-gathered
    "~/Downloads/data/read-test/RK-20240729-175543-E2.0.nc.txz",  # CF-1.7 from RadarKit
    "~/Downloads/data/read-test/PX-20241221-125419-E6.0.txz",  # CF-1.7 from RadarKit
    "~/Downloads/data/read-test/PX-20241221-125419-E6.0.nc",  # CF-1.7 from RadarKit
    "~/Downloads/data/read-test/BS1-20230616-020024-E6.4.txz",  # CF-2 in txz
    "~/Downloads/data/read-test/cfrad.20150625_050022_PX1000_v35_s1.nc",  # David's convention
    "~/Downloads/data/read-test/cfrad.20080604_002217_000_SPOL_v36_SUR.nc",  # From open-radar-data
    "~/Downloads/data/read-test/cfrad.20211011_201557.188_to_20211011_201617.720_DOW8_PPI.nc",  # From open-radar-data
    "~/Downloads/data/read-test/cfrad.20211011_201711.345_to_20211011_201732.860_DOW8_PPI.nc",  # From open-radar-data
    "~/Downloads/data/read-test/KTLX20250217_204640_V06",  # NEXRAD L2 VOLUME
    "~/Downloads/data/read-test/KTLX-20250503-165233-900-1-S",  # NEXRAD L2-BZIP2 LDM
]

tic = time.time()
fifo = radar.FIFOBuffer()
for file in files:
    path = os.path.expanduser(file)
    req = threading.Thread(target=request, args=(client, path))
    req.start()
    fifo.enqueue(req)
    while fifo.size() >= client.count * 2:
        req = fifo.dequeue()
        req.join()
    # Simulate a random delay
    if SIMULATE_DELAY:
        period = random.randint(0, 13)
        logger.debug(f"Sleeping for {period} second{'s' if period > 1 else ''} ...")
        client._shallow_sleep(period)
for req in fifo.queue:
    req.join()
toc = time.time()

print(f"Elapsed: {toc - tic:.3f} s")

print("Getting stats ...")
stats = client.stats()
print(f"stats: {stats}")

client.close()
