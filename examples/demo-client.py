import os
import sys
import glob
import time
import random
import logging
import threading

srcDir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
if os.path.exists(srcDir):
    print(f"Inserting {srcDir} into sys.path")
    sys.path.insert(0, srcDir)

import radar

logger = logging.getLogger("demo-client")

SIMULATE_DELAY = False


def request(client, file):
    logger.info(f"Req: {file} ...")
    data = client.get(file)
    if data is None:
        logger.info(f"Ign: {file} ...")
        return None
    unixTime = data["time"]
    timeString = time.strftime(r"%Y%m%d-%H%M%S", time.localtime(unixTime))
    basename = os.path.basename(file)
    elements = basename.split("-")
    fileTime = f"{elements[1]}-{elements[2]}"
    mark = radar.cosmetics.check if fileTime == timeString else radar.cosmetics.cross
    logger.info(f"Out: {basename} / {timeString} {mark}")
    return data


###

fileHandler = logging.FileHandler(os.path.expanduser("~/logs/demo-client.log"))
fileHandler.setFormatter(radar.log_formatter)
logger.addHandler(fileHandler)
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(radar.log_formatter)
logger.addHandler(streamHandler)
logger.setLevel(logging.INFO)

logger.info("Starting ...")

client = radar.product.Client(count=6, logger=logger)

# Replace with where the data is stored
# files = sorted(glob.glob("/mnt/data/PX1000/2024/20240820/_original/*xz"))
files = sorted(glob.glob("/Volumes/Data/PX1000/2024/20240820/_original/*xz"))

tic = time.time()
fifo = radar.FIFOBuffer()
for file in files[-200:-100]:
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
