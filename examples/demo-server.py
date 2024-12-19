import os
import time
import logging

import src.radar as radar

if __name__ == "__main__":

    logger = logging.getLogger("demo-server")
    fileHandler = logging.FileHandler(os.path.expanduser("~/logs/demo-server.log"))
    fileHandler.setFormatter(radar.logFormatter)
    logger.addHandler(fileHandler)
    streamHandler = logging.StreamHandler()
    streamHandler.setLevel(logging.INFO)
    logger.addHandler(streamHandler)
    logger.setLevel(logging.INFO)

    if bool(os.environ.get("DJANGO_DEBUG")):
        server = radar.product.Server(n=8, logger=logger, cache=200, port=6969)
    else:
        server = radar.product.Server(logger=logger)
    server.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("KeyboardInterrupt ...")
        pass

    print("done")
