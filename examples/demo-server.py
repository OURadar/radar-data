import os
import time
import logging

import radar

logger = logging.getLogger("demo-server")
fileHandler = logging.FileHandler(os.path.expanduser("~/logs/demo-server.log"))
fileHandler.setFormatter(radar.logFormatter)
logger.addHandler(fileHandler)
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.INFO)
logger.addHandler(streamHandler)
logger.setLevel(logging.INFO)

server = radar.product.Server(logger=logger)
server.start()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print("KeyboardInterrupt ...")
    pass
except:
    print("Something else")
    pass

print("done")
