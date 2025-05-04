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
    elements = basename.split("-")
    fileTime = f"{elements[1]}-{elements[2]}"
    mark = radar.cosmetics.check if fileTime == timeString else radar.cosmetics.cross
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
# else:
files = sorted(glob.glob(os.path.expanduser("~/Downloads/data/read-test/PX*")))

tic = time.time()
fifo = radar.FIFOBuffer()
for file in files:
    req = threading.Thread(target=request, args=(client, file))
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
