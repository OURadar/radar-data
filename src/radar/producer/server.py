import os
import json
import time
import radar
import pickle
import signal
import socket
import logging
import threading
import multiprocess as mp

from setproctitle import setproctitle, getproctitle

from .cosmetics import colorize, pretty_object_name
from .lrucache import LRUCache

from .const import CHANNEL
from .share import send, recv, clamp

cache = None
logger = None


class Server:
    def __init__(self, n=8, **kwargs):
        self.name = colorize("Server", "green")
        self.clients = {}
        self.tasked = {}
        self.lock = threading.Lock()
        self.mpLock = mp.Lock()
        self.taskQueue = mp.Queue()
        self.dataQueue = mp.Queue()
        self.readerRun = mp.Value("i", 0)
        self.publisherRun = mp.Value("i", 1)
        self.connectorRun = mp.Value("i", 1)
        self.n = clamp(n, 2, 16)
        global cache, logger
        cache = LRUCache(kwargs.get("cache", 1000))
        logger = kwargs.get("logger", logging.getLogger("product"))
        self._host = kwargs.get("host", "0.0.0.0")
        self._port = kwargs.get("port", 50000)
        # Wire things up
        self.readerThreads = []
        for k in range(self.n):
            worker = mp.Process(target=self._reader, args=(k,))
            self.readerThreads.append(worker)
        self.publisherThreads = []
        for k in range(2):
            worker = threading.Thread(target=self._publisher, args=(k,))
            self.publisherThreads.append(worker)
        self.connectorThread = threading.Thread(target=self._connector)
        if kwargs.get("signal", False):
            self._originalSigIntHandler = signal.getsignal(signal.SIGINT)
            self._originalSigTermHandler = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGINT, self._signalHandler)
            signal.signal(signal.SIGTERM, self._signalHandler)

    def _reader(self, id):
        myname = pretty_object_name("Server.reader", f"{id:02d}")
        setproctitle(f"{getproctitle()} # Server.reader[{id}]")
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
        while self.publisherRun.value:
            try:
                result = self.dataQueue.get(timeout=0.05)
                fileno = result["fileno"]
                if fileno not in self.clients:
                    logger.warn(f"{myname} Client {fileno} not found")
                    continue
                clientSocket = self.clients[fileno]
                name = os.path.basename(result["path"])
                data = result["data"]
                # data = zlib.compress(data)
                # cache.put(name, data, compress=False)
                cache.put(name, data)
                clientSocket.settimeout(1.0)
                send(clientSocket, data)
                logger.info(f"{myname} {tag}: {name} ({len(data):,d} B) <{fileno}>")
                self.tasked[fileno] = False
                result.task_done()
            except:
                pass
        logger.info(f"{myname} Stopped")

    def _concierge(self, clientSocket):
        fileno = clientSocket.fileno()
        myname = pretty_object_name("Server.concierge", fileno)
        logger.info(f"{myname} Started")
        tag = colorize("Cache", "orange")
        while self.publisherRun.value:
            clientSocket.settimeout(0.1)
            try:
                request = recv(clientSocket)
                if not request:
                    break
                request = json.loads(request)
                clientSocket.settimeout(1.0)
                if "path" in request:
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
                while self.tasked[fileno] and self.connectorRun.value:
                    time.sleep(0.05)
            except:
                pass
        with self.lock:
            del self.clients[fileno]
            del self.tasked[fileno]
        clientSocket.close()
        logger.info(f"{myname} Stopped")

    def _connector(self):
        myname = colorize("Server.connector", "green")
        sd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sd.bind((self._host, self._port))
        sd.settimeout(0.1)
        sd.listen(self.n)
        logger.info(f"{myname} Started")
        while self.connectorRun.value:
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
        while self.readerRun.value < self.n:
            time.sleep(0.02)
        for worker in self.publisherThreads:
            worker.start()
        self.connectorThread.start()

    def _signalHandler(self, signum, frame):
        myname = colorize("Server.signalHandler", "green")
        signalName = {2: "SIGINT", 10: "SIGUSR1", 15: "SIGTERM"}
        print("")
        logger.info(f"{myname} {signalName.get(signum, 'UNKNOWN')} received")
        self.stop(callback=self._afterStop, args=(signum, frame))

    def _afterStop(self, signum, frame):
        if signum == signal.SIGINT and self._originalSigIntHandler:
            self._originalSigIntHandler(signum, frame)
        if signum == signal.SIGTERM and self._originalSigTermHandler:
            self._originalSigTermHandler(signum, frame)

    def start(self, delay=0.1):
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
        self.publisherRun.value = 0
        for worker in self.publisherThreads:
            worker.join()
        logger.debug(f"{self.name} Stopping connector ...")
        self.connectorRun.value = 0
        self.connectorThread.join()
        logger.info(f"{self.name} Stopped")
        if callback:
            callback(*args)
        return 0
