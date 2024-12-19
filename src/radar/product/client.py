import json
import pickle
import socket
import logging
import threading

from .share import *
from ..cosmetics import colorize, pretty_object_name

logger = None


class Client(Manager):
    def __init__(self, n=1, **kwargs):
        super().__init__(n, **kwargs)
        self.name = colorize("Client", "green")
        self._host = kwargs.get("host", "localhost")
        self._i = 0
        global logger
        logger = self.logger
        # Wire things up
        self.sockets = []
        self.connectThread = threading.Thread(target=self._connect)
        self.connectThread.start()
        while self.wantActive and len(self.sockets) < self.n:
            time.sleep(0.1)

    def _getSocketAndLock(self):
        with self.lock:
            i = self._i
            self._i = (i + 1) % self.n
        sock = self.sockets[i]
        lock = self.clientLocks[i]
        return sock, lock

    def _connect(self):
        myname = colorize("Client.connect", "green")
        while self.wantActive:
            with self.lock:
                # Make n connections
                self._i = 0
                self.sockets = []
                for _ in range(self.n):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    logger.info(f"Socker[{sock.fileno()}] Connecting to {self._host}:{self._port} ...")
                    try:
                        sock.settimeout(1.0)
                        sock.connect((self._host, self._port))
                    except ConnectionRefusedError:
                        logger.info(f"{myname} Connection failed ...")
                        break
                    self.sockets.append(sock)
            if len(self.sockets) == 0:
                self._shallow_sleep(5.0)
                continue
            # Keep running until told to stop
            ping = 0
            while self.wantActive:
                for sock, lock in zip(self.sockets, self.clientLocks):
                    k = sock.fileno()
                    with lock:
                        sock.settimeout(5.0)
                        logger.debug(f"{myname} sockets[{k}] ping[{ping}] ...")
                        try:
                            send(sock, json.dumps({"ping": ping}).encode())
                        except BrokenPipeError:
                            data = None
                            break
                        try:
                            data = recv(sock)
                        except ConnectionResetError:
                            data = None
                        except:
                            logger.error(f"{myname} sockets[{k}] unexpected error")
                            data = None
                    if data is None:
                        logger.info(f"{myname} sockets[{k}] server not available")
                        break
                if data is None:
                    break
                self._shallow_sleep(10.0)
                ping += 1
            for sock in self.sockets:
                sock.close()

    def get(self, path, tarinfo=None):
        if self.sockets == []:
            logger.info(f"{self.name} Not connected")
            return None
        sock, lock = self._getSocketAndLock()
        with lock:
            sock.settimeout(5.0)
            try:
                send(sock, json.dumps({"path": path, "tarinfo": tarinfo}).encode())
                data = recv(sock)
            except BrokenPipeError:
                myname = pretty_object_name("Client.get", sock.fileno())
                logger.warning(f"{myname} BrokenPipeError")
                data = None
        if data is None:
            myname = pretty_object_name("Client.get", sock.fileno())
            logger.error(f"{myname} Server not available")
            self.wakeUp = True
            return None
        return pickle.loads(data)

    def stats(self):
        if self.sockets == []:
            logger.info(f"{self.name} Not connected")
            return None
        sock, lock = self._getSocketAndLock()
        with lock:
            sock.settimeout(5.0)
            send(sock, json.dumps({"stats": 1}).encode())
            message = recv(sock)
            if message is None:
                myname = colorize("Client.stats()", "green")
                logger.error(f"{myname} No message")
                return None
        return message.decode("utf-8")

    def close(self):
        self.wantActive = False
        self.connectThread.join()
