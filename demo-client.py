import os
import glob
import time
import random
import logging
import threading

import src.radar as radar

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

if __name__ == "__main__":

    fileHandler = logging.FileHandler(os.path.expanduser("~/logs/producer.log"))
    fileHandler.setFormatter(radar.logFormatter)
    logger.addHandler(fileHandler)
    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(radar.logFormatter)
    logger.addHandler(streamHandler)
    logger.setLevel(logging.INFO)

    logger.info("Starting ...")

    if bool(os.environ.get("DJANGO_DEBUG")):
        client = radar.product.Client(n=6, port=6969, logger=logger)
    else:
        client = radar.product.Client(n=6, logger=logger)

    files = sorted(glob.glob("/mnt/data/PX1000/2024/20240820/_original/*xz"))

    tic = time.time()
    fifo = radar.FIFOBuffer()
    for file in files[-200:-100]:
        # file = file.replace("/mnt/data", "/Volumes/Data")
        req = threading.Thread(target=request, args=(client, file))
        req.start()
        fifo.enqueue(req)
        while fifo.size() >= client.n * 2:
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
