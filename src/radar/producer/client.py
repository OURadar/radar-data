import json
import pickle
import socket
import logging
import threading

from .cosmetics import colorize, pretty_object_name
from .share import send, recv, clamp

logger = None


class Client:
    def __init__(self, n=1, **kwargs):
        self.name = colorize("Client", "green")
        self.lock = threading.Lock()
        self.n = clamp(n, 1, 16)
        global logger
        logger = kwargs.get("logger", logging.getLogger("product"))
        self._host = kwargs.get("host", "localhost")
        self._port = kwargs.get("port", 50000)
        # Wire things up
        self._i = 0
        self.sockets = []
        for _ in range(self.n):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self._host, self._port))
            self.sockets.append(sock)
        self.locks = [threading.Lock() for _ in range(self.n)]

    def get_id(self):
        with self.lock:
            i = self._i
            self._i = (i + 1) % self.n
        return i

    def get(self, path, tarinfo=None):
        i = self.get_id()
        lock = self.locks[i]
        sock = self.sockets[i]
        with lock:
            send(sock, json.dumps({"path": path, "tarinfo": tarinfo}).encode())
            data = recv(sock)
            if data is None:
                myname = pretty_object_name("Client.get", i)
                logger.error(f"{myname} No data")
                return None
            # data = zlib.decompress(data)
        return pickle.loads(data)

    def stats(self):
        i = self.get_id()
        lock = self.locks[i]
        sock = self.sockets[i]
        with lock:
            send(sock, json.dumps({"stats": 1}).encode())
            message = recv(sock)
            if message is None:
                myname = colorize("Client.stats()", "green")
                logger.error(f"{myname} No message")
                return None
        return message.decode("utf-8")

    def close(self):
        for sock in self.sockets:
            sock.close()
