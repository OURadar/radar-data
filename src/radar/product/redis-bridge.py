"""
This is not used. It is a reference to the original implementation of the Server & Client classes.
"""

import os
import json
import time
import radar
import redis
import pickle
import signal
import logging
import threading
import multiprocess as mp

from setproctitle import setproctitle, getproctitle

from ..cosmetics import colorize, pretty_object_name
from ..lrucache import LRUCache

from .const import CHANNEL
from .share import clamp

cache = None
logger = None

# Not recommended. Keep here for reference


class ServerRedis:
    def __init__(self, n=8, **kwargs):
        self.name = colorize("ServerRedis", "green")
        self.relay = redis.StrictRedis()
        self.pubsub = self.relay.pubsub()
        self.taskQueue = mp.Queue()
        self.dataQueue = mp.Queue()
        self.run = mp.Value("i", 1)
        self.n = clamp(n, 2, 16)
        global cache, logger
        cache = LRUCache(kwargs.get("cache", 1000))
        logger = kwargs.get("logger", logging.getLogger("product"))
        # Wire things up
        self.readers = []
        self.requestHandlers = []
        self.responseHandlers = []
        for k in range(self.n):
            worker = mp.Process(target=self._reader, args=(k,))
            self.readers.append(worker)
        for k in range(self.n // 2):
            worker = threading.Thread(target=self._responseHandler, args=(k,))
            self.responseHandlers.append(worker)
        worker = threading.Thread(target=self._requestHandler, args=(0,), daemon=True)
        self.requestHandlers.append(worker)
        if kwargs.get("signal", False):
            signal.signal(signal.SIGTERM, self._signalHandler)

    def _reader(self, id):
        myname = pretty_object_name("ServerRedis.reader", id)
        setproctitle(f"{getproctitle()} # ServerRedis.reader[{id}]")
        logger.info(f"{myname} Started")
        while self.run.value:
            try:
                request = self.taskQueue.get_nowait()
                if request is None or "path" not in request:
                    continue
                channel = request["channel"]
                path = request["path"]
                data = radar.read(path, tarinfo=request.get("tarinfo", None))
                data = pickle.dumps(data)
                logger.debug(f"{myname} {path}")
                self.dataQueue.put({"channel": channel, "path": path, "data": data})
                request.task_done()
            except KeyboardInterrupt:
                break
            except:
                time.sleep(0.05)
        logger.info(f"{myname} Stopped")

    def _requestHandler(self, id):
        myname = pretty_object_name(f"ServerRedis.request", id)
        self.pubsub.subscribe(CHANNEL)
        tag = colorize("Cache", "orange")
        logger.info(f"{myname} Started")
        while self.run.value:
            for post in self.pubsub.listen():
                if post["type"] != "message":
                    continue
                info = json.loads(post["data"])
                channel = info["channel"]
                if "path" in info:
                    name = os.path.basename(info["path"])
                    logger.info(f"{myname} Sweep: {name} {channel}")
                    data = cache.get(name)
                    if data is None:
                        # Queue it up for reader, _responseHandler() will respond
                        self.taskQueue.put(info)
                    else:
                        # Respond immediately from cache
                        self.relay.publish(channel, data)
                        logger.info(f"{myname} {tag}: {name} ({len(data):,d} B)")
                elif "stats" in info:
                    self.relay.publish(channel, cache.size())
        logger.info(f"{myname} Stopped")

    def _responseHandler(self, id):
        myname = pretty_object_name(f"ServerRedis.respond", id)
        logger.info(f"{myname} Started")
        tag = colorize("Drive", "skyblue")
        while self.run.value:
            try:
                result = self.dataQueue.get_nowait()
                if result is None:
                    continue
                channel = result["channel"]
                data = result["data"]
                name = os.path.basename(result["path"])
                cache.put(name, data)
                logger.info(f"{myname} {tag}: {name} ({len(data):,d} B)")
                self.relay.publish(channel, data)
                result.task_done()
            except KeyboardInterrupt:
                break
            except:
                time.sleep(0.05)
        logger.info(f"{myname} Stopped")

    def _delayStart(self):
        time.sleep(1)
        self.run.value = 1
        for worker in self.readers:
            worker.start()
        for worker in self.requestHandlers:
            worker.start()
        for worker in self.responseHandlers:
            worker.start()

    def _signalHandler(self, signum, frame):
        logger.debug(f"{self.name} signalHandler {signum} / {frame}")
        self.stop()

    def start(self):
        threading.Thread(target=self._delayStart).start()

    def stop(self):
        logger.info(f"{self.name} Stopping ...")
        for buf in self.buffers:
            buf.close()
            buf.unlink()
        self.run.value = 0
        self.pubsub.close()


class ClientRedis:
    def __init__(self):
        self.name = "ClientRedis"
        self.relay = redis.StrictRedis()
        self.pubsub = self.relay.pubsub()

    def get(self, path, tarinfo=None):
        relay = redis.StrictRedis()
        pubsub = relay.pubsub()
        channel = uuid.uuid4().hex[:16]
        pubsub.subscribe(channel)
        relay.publish(CHANNEL, json.dumps({"path": path, "tarinfo": tarinfo, "channel": channel}))
        for message in pubsub.listen():
            if message["type"] == "message":
                data = pickle.loads(message["data"])
                break
        pubsub.unsubscribe(channel)
        return data

    def stats(self):
        channel = uuid.uuid4().hex[:16]
        self.pubsub.subscribe(channel)
        self.relay.publish(CHANNEL, json.dumps({"stats": True, "channel": channel}))
        for message in self.pubsub.listen():
            if message["type"] == "message":
                info = message["data"].decode("utf-8")
                break
        self.pubsub.unsubscribe(channel)
        return info
