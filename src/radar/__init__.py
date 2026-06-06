__version__ = "1.4.3"

import importlib

from .common import *


_sub_ = ["chart", "cosmetics", "product"]
_misc_ = ["print", "FIFOBuffer"]
_read_ = ["read", "read_tarinfo", "set_logger"]
_write_ = ["write"]

def __dir__():
    return sorted(list(globals().keys()) + _sub_ + _read_ + _write_ +_misc_)

def __getattr__(name):
    if name in _sub_:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    elif name in _read_:
        module = importlib.import_module(".read", __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    elif name in _write_:
        module = importlib.import_module(".write", __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    elif name == "FIFOBuffer":
        module = importlib.import_module(".fifobuffer", __name__)
        value = module.FIFOBuffer
        globals()[name] = value
        return value
    elif name == "print":
        module = importlib.import_module(".cosmetics", __name__)
        value = module.dict_print
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
