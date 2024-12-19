import os
import json
import time
import radar
import pickle
import signal
import socket
import threading
import multiprocess as mp

from setproctitle import setproctitle, getproctitle

from .share import *
from ..cosmetics import colorize, pretty_object_name
from ..lrucache import LRUCache


cache = None
logger = None


# Each worker is a separate process because data reader is not thread safe (limitation of HDF5)

# - _connector runs a single thread to accept incoming connections
# - _concierge runs a single thread to handle a client connection
# - _reader runs multiple processes to read data from disk
# - _publisher runs multiple threads to send data to clients


class Server(Manager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = colorize("Server", "green")
        self._host = kwargs.get("host", "0.0.0.0")
        global cache, logger
        cache = LRUCache(kwargs.get("cache", 1000))
        logger = self.logger
        # Wire things up
        self.clients = {}
        self.tasked = {}
        self.mpLock = mp.Lock()
        self.taskQueue = mp.Queue()
        self.dataQueue = mp.Queue()
        self.readerRun = mp.Value("i", 0)
        self.readerThreads = []
        for k in range(self.count):
            worker = mp.Process(target=self._reader, args=(k,))
            self.readerThreads.append(worker)
        self.publisherThreads = []
        for k in range(2):
            worker = threading.Thread(target=self._publisher, args=(k,))
            self.publisherThreads.append(worker)
        self.connectorThread = threading.Thread(target=self._listen)

    def _reader(self, id):
        myname = pretty_object_name("Server.reader", f"{id:02d}")
        setproctitle(f"{getproctitle()} # reader[{id}]")
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        with self.mpLock:
            self.readerRun.value += 1
        logger.info(f"{myname} Started")
        while self.readerRun.value:
            try:
                request = self.taskQueue.get(timeout=0.05)
                if request is None or "path" not in request:
                    logger.info(f"{myname} No request")
                    continue
                tarinfo = request.get("tarinfo", None)
                fileno = request["fileno"]
                path = request["path"]
                data = radar.read(path, tarinfo=tarinfo)
                data = pickle.dumps(data)
                self.dataQueue.put({"fileno": fileno, "path": path, "data": data})
                request.task_done()
            except:
                pass
        logger.info(f"{myname} Stopped")

    def _publisher(self, id):
        # myname = colorize(f"Server.publisher", "green")
        myname = pretty_object_name("Server.publisher", f"{id:02d}")
        logger.info(f"{myname} Started")
        tag = colorize("Drive", "skyblue")
        while self.wantActive:
            try:
                result = self.dataQueue.get(timeout=0.05)
                fileno = result["fileno"]
                if fileno not in self.clients:
                    logger.warn(f"{myname} Client {fileno} not found")
                    continue
                sock = self.clients[fileno]
                name = os.path.basename(result["path"])
                data = result["data"]
                cache.put(name, data)
                sock.settimeout(1.0)
                send(sock, data)
                logger.info(f"{myname} {tag}: {name} ({len(data):,d} B) <{fileno}>")
                self.tasked[fileno] = False
                result.task_done()
            except:
                # Timeout just means there's no data to publish
                pass
        logger.info(f"{myname} Stopped")

    def _concierge(self, clientSocket):
        fileno = clientSocket.fileno()
        myname = pretty_object_name("Server.concierge", fileno)
        logger.info(f"{myname} Started")
        tag = colorize("Cache", "orange")
        assert fileno in self.clients, f"{myname} Client {fileno} not found"
        while self.wantActive:
            try:
                clientSocket.settimeout(0.1)
                request = recv(clientSocket)
                if not request:
                    logger.debug(f"{myname} client disconnected")
                    break
                request = json.loads(request)
                logger.debug(f"{myname} {request}")
                if "ping" in request:
                    send(clientSocket, json.dumps({"pong": request["ping"]}).encode())
                    continue
                elif "path" in request:
                    name = os.path.basename(request["path"])
                    # data = cache.get(name, decompress=False)
                    data = cache.get(name)
                    logger.info(f"{myname} Sweep: {name}")
                    if data is None:
                        # Queue it up for reader, and let _publisher() respond
                        request["fileno"] = fileno
                        self.tasked[fileno] = True
                        self.taskQueue.put(request)
                    else:
                        # Respond immediately from cache
                        logger.info(f"{myname} {tag}: {name} ({len(data):,d} B)")
                        send(clientSocket, data)
                        self.tasked[fileno] = False
                elif "stats" in request:
                    send(clientSocket, str(cache.size()).encode())
                # Wait for publisher to respond before taking another request
                while self.tasked[fileno] and self.wantActive:
                    time.sleep(0.05)
            except TimeoutError:
                continue
            except:
                break
        with self.lock:
            del self.clients[fileno]
            del self.tasked[fileno]
        clientSocket.close()
        logger.info(f"{myname} Stopped")

    def _listen(self):
        myname = colorize("Server.listen", "green")
        sd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sd.bind((self._host, self._port))
        sd.settimeout(0.25)
        sd.listen(32)
        logger.info(f"{myname} Started")
        while self.wantActive:
            try:
                cd, (addr, port) = sd.accept()
            except socket.timeout:
                continue
            except:
                raise
            with self.lock:
                fileno = cd.fileno()
                self.clients[fileno] = cd
                self.tasked[fileno] = False
            logger.info(f"{myname} Connection from {addr}:{port} / {cd.fileno()}")
            threading.Thread(target=self._concierge, args=(cd,)).start()
        sd.close()
        logger.info(f"{myname} Stopped")

    def _delayStart(self, delay):
        time.sleep(delay)
        for worker in self.readerThreads:
            worker.start()
        while self.readerRun.value < self.count:
            time.sleep(0.02)
        for worker in self.publisherThreads:
            worker.start()
        self.connectorThread.start()

    def start(self, delay=0.1):
        self.wantActive = True
        threading.Thread(target=self._delayStart, args=(delay,), daemon=True).start()

    def stop(self, callback=None, args=()):
        with self.mpLock:
            if self.readerRun.value == 0:
                return 1
            self.readerRun.value = 0
        logger.debug(f"{self.name} Stopping readers ...")
        for worker in self.readerThreads:
            worker.join()
        logger.debug(f"{self.name} Stopping publisher ...")
        self.wantActive = False
        for worker in self.publisherThreads:
            worker.join()
        logger.debug(f"{self.name} Stopping connector ...")
        self.connectorThread.join()
        logger.info(f"{self.name} Stopped")
        super().stop(callback, args)
        return 0

    def join(self):
        for worker in self.readerThreads:
            worker.join()
        for worker in self.publisherThreads:
            worker.join()
        self.connectorThread.join()
        return 0
