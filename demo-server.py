import time
import logging

import src.radar as radar

if __name__ == "__main__":

    logger = logging.getLogger("demo-server")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

    server = radar.product.Server(n=8, logger=logger, cache=200, port=6969)
    server.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("KeyboardInterrupt ...")
        pass

    print("done")
