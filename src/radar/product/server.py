import os
import glob
import json
import time
import radar
import pickle
import signal
import socket
import threading
import multiprocess as mp

# import multiprocessing as mp

from setproctitle import setproctitle, getproctitle

from .share import *
from ..cosmetics import colorize, pretty_object_name
from ..lrucache import LRUCache


logger = None


# Each reader is a separate process because data reader is not thread safe (limitation of HDF5)


class Conceirge:
    busy = False

    def __init__(self, parent, fileno, **kwargs):
        self._parent = parent
        self._fileno = fileno
        self._addr = kwargs.get("addr", "0.0.0.0")

    def _runloop(self):
        sock = self._parent.clients[self._fileno]
        outQueue = self._parent.outQueue[self._fileno]
        jobQueue = self._parent.jobQueue
        cache = self._parent.cache
        myname = pretty_object_name("Server.concierge", self._fileno)
        cacheTag = colorize("Cache", "orange")
        driveTag = colorize("Drive", "skyblue")

        logger.info(f"{myname} Started for {self._addr[0]}:{self._addr[1]}")

        while self._parent.wantActive:
            # Input / incoming requests
            try:
                sock.settimeout(0.05)
                request = recv(sock)
                if not request:
                    logger.debug(f"{myname} Client disconnected")
                    break
                request = json.loads(request)
                logger.debug(f"{myname} {request}")
                sock.settimeout(2.5)
                if "ping" in request:
                    send(sock, json.dumps({"pong": request["ping"]}).encode())
                elif "path" in request:
                    name = os.path.basename(request["path"])
                    logger.info(f"{myname} Sweep: {name}")
                    blob = cache.get(name)
                    if blob is None:
                        # Queue it up for reader. Collector will put it in outQueue when ready
                        jobQueue.put({"fileno": self._fileno, "path": request["path"]})
                        self.busy = True
                    else:
                        # Respond with cached data
                        logger.info(f"{myname} {cacheTag}: {name} ({len(blob):,d} B)")
                        send(sock, blob)
                elif "stats" in request:
                    send(sock, str(cache.size()).encode())
                elif "execute" in request:
                    command = request["execute"]
                    folder = request.get("folder", None)
                    if command == "list" and folder:
                        logger.info(f"{myname} Listing folder {folder}")
                        files = sorted(glob.glob(os.path.join(folder, "[A-Za-z0-9]*z")))
                        payload = json.dumps(files).encode()
                        send(sock, payload)
                    else:
                        logger.debug(f"{myname} Unable to process custom request")
                else:
                    logger.warning(f"{myname} Unknown request")
            except TimeoutError:
                if self._parent.wantActive:
                    time.sleep(0.05)
            except Exception as e:
                logger.error(f"{myname} {e}")
                break
            # Ouput / data delivery
            if not self.busy:
                continue
            try:
                result = outQueue.get(timeout=0.05)
                fileno = result["fileno"]
                if fileno != self._fileno:
                    logger.warning(f"{myname} Client {fileno} mismatch")
                    continue
                # Use basname to as key to cache
                name = os.path.basename(result["path"])
                blob = result["blob"]
                cache.put(name, blob)
                sock.settimeout(2.5)
                send(sock, blob)
                self.busy = False
                logger.info(f"{myname} {driveTag}: {name} ({len(blob):,d} B)")
                result.task_done()
            except:
                if self._parent.wantActive:
                    time.sleep(0.05)

        sock.close()
        with self._parent.lock:
            del self._parent.clients[self._fileno]
            del self._parent.outQueue[self._fileno]
        logger.info(f"{myname} Stopped")

    def start(self):
        threading.Thread(target=self._runloop, daemon=True).start()


def _reader(id, workQueue, dataQueue, lock, wantActive):
    myname = pretty_object_name("Server.reader", f"{id:02d}")
    setproctitle(f"{getproctitle()} # reader[{id}]")
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with lock:
        wantActive.value += 1
    logger.info(f"{myname} Started")
    while wantActive.value:
        try:
            request = workQueue.get(timeout=0.05)
            if request is None or "path" not in request:
                logger.info(f"{myname} No request")
                continue
            tarinfo = request.get("tarinfo", None)
            fileno = request["fileno"]
            path = request["path"]
            data, tarinfo = radar.read(path, tarinfo=tarinfo, want_tarinfo=True)
            blob = pickle.dumps({"data": data, "tarinfo": tarinfo})
            dataQueue.put({"fileno": fileno, "path": path, "blob": blob})
            request.task_done()
        except:
            pass
    logger.info(f"{myname} Stopped")


class Server(Manager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._host = kwargs.get("host", "0.0.0.0")
        self.name = pretty_object_name("Server", self._host, self._port)
        # Wire things up
        global logger
        logger = self.logger
        self.cache = LRUCache(kwargs.get("cache", 1000))
        self.clients = {}
        # Multiprocessing.
        # IMPORTANT: Do not share cache across processes
        self.mpLock = mp.Lock()
        self.mpWantActive = mp.Value("i", 0)
        self.jobQueue = mp.Queue()  # Request queue for readers to pick up
        self.midQueue = mp.Queue()  # Middle data queue for readers to put data
        self.outQueue = {}  # Output queue for concierges to get data to deliver, fileno as key
        self.workers = []
        for k in range(self.count):
            w = mp.Process(target=_reader, args=(k, self.jobQueue, self.midQueue, self.mpLock, self.mpWantActive))
            self.workers.append(w)
        # Threading
        self.connectorThread = threading.Thread(target=self._connector)
        self.collectorThread = threading.Thread(target=self._collector)
        logger.info(self.name)

    def _connector(self):
        myname = colorize("Server.connector", "green")
        sd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sd.bind((self._host, self._port))
        sd.settimeout(0.05)
        sd.listen(32)
        logger.info(f"{myname} Started")
        while self.wantActive:
            try:
                cd, addr = sd.accept()
            except socket.timeout:
                if self.wantActive:
                    time.sleep(0.05)
                continue
            except Exception as e:
                logger.warning(f"{myname} Socket accept failed {e}")
                raise
            with self.lock:
                fileno = cd.fileno()
                self.clients[fileno] = cd
                self.outQueue[fileno] = mp.Queue()
                concierge = Conceirge(self, fileno, addr=addr)
                concierge.start()
        sd.close()
        logger.info(f"{myname} Stopped")

    def _collector(self):
        myname = colorize("Server.collector", "green")
        logger.info(f"{myname} Started")
        while self.wantActive:
            try:
                result = self.midQueue.get(timeout=0.05)
                fileno = result["fileno"]
                if fileno not in self.outQueue:
                    logger.warning(f"{myname} Client {fileno} not found")
                    continue
                self.outQueue[fileno].put(result)
            except:
                # Technically getting _queue.Empty but not in the namespace
                pass
        logger.info(f"{myname} Stopped")

    def _delayStart(self, delay):
        time.sleep(delay)
        for worker in self.workers:
            worker.start()
        while self.mpWantActive.value < self.count:
            time.sleep(0.02)
        self.connectorThread.start()
        self.collectorThread.start()

    def start(self, delay=0.1):
        self.wantActive = True
        threading.Thread(target=self._delayStart, args=(delay,), daemon=True).start()

    def stop(self, callback=None, args=()):
        with self.mpLock:
            if self.mpWantActive.value == 0:
                return 1
            self.mpWantActive.value = 0
        logger.debug(f"{self.name} Stopping ...")
        for worker in self.workers:
            worker.join()
        self.wantActive = False
        self.join()
        logger.info(f"{self.name} Stopped")
        super().stop(callback, args)

    def join(self):
        logger.debug("Waiting for all threads to join ...")
        for worker in self.workers:
            worker.join()
        self.connectorThread.join()
        self.collectorThread.join()
        logger.info(f"{self.name} Joined")
