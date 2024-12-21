import os
import sys
import time
import logging

srcDir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
if os.path.exists(srcDir):
    print(f"Inserting {srcDir} into sys.path")
    sys.path.insert(0, srcDir)

import radar

logger = logging.getLogger("demo-server")
fileHandler = logging.FileHandler(os.path.expanduser("~/logs/demo-server.log"))
fileHandler.setFormatter(radar.log_formatter)
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
