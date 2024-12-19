import time
import signal
import struct
import logging
import threading

from ..cosmetics import colorize
from .const import COUNT, PORT


def send(socket, data):
    payload = struct.pack(">I", len(data)) + data
    socket.sendall(payload)


def recv(socket):
    head = socket.recv(4)
    if not head:
        return None
    elif head == b"ping":
        socket.sendall(b"pong\r\n")
        return None
    size = struct.unpack(">I", head)[0]
    data = bytearray()
    while len(data) < size:
        blob = socket.recv(size - len(data))
        if not blob:
            break
        data.extend(blob)
    return data


def clamp(x, lo, hi):
    return max(lo, min(x, hi))


class Manager:
    def __init__(self, **kwargs):
        self.name = colorize("Manager", "green")
        self._port = kwargs.get("port", PORT)
        self.count = clamp(kwargs.get("count", COUNT), 2, 16)
        self.lock = threading.Lock()
        self.clientLocks = [threading.Lock() for _ in range(self.count)]
        self.logger = kwargs.get("logger", logging.getLogger("producer"))
        self.verbose = kwargs.get("verbose", 0)
        self.wakeUp = False
        self.wantActive = True
        if kwargs.get("signal", True):
            self._originalSigIntHandler = signal.getsignal(signal.SIGINT)
            self._originalSigTermHandler = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGINT, self._signalHandler)
            signal.signal(signal.SIGTERM, self._signalHandler)

    def _signalHandler(self, signum, frame):
        myname = self.name + colorize("._signalHandler", "green")
        signalName = {2: "SIGINT", 10: "SIGUSR1", 15: "SIGTERM"}
        print("")
        self.wantActive = False
        self.logger.info(f"{myname} {signalName.get(signum, 'UNKNOWN')} received")
        self.stop(callback=self._afterStop, args=(signum, frame))

    def _afterStop(self, signum, frame):
        if signum == signal.SIGINT and self._originalSigIntHandler:
            self._originalSigIntHandler(signum, frame)
        if signum == signal.SIGTERM and self._originalSigTermHandler:
            self._originalSigTermHandler(signum, frame)

    def _shallow_sleep(self, seconds):
        self.wakeUp = False
        for _ in range(int(seconds * 10.0)):
            if self.wakeUp or not self.wantActive:
                break
            time.sleep(0.1)

    def start(self):
        self.wantActive = True
        pass

    def stop(self, callback=None, args=()):
        self.wantActive = False
        if callback:
            callback(*args)
