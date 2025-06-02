__version__ = "1.2"

from .common import *
from .fifobuffer import FIFOBuffer
from .read import read, read_tarinfo, set_logger

from . import cosmetics
from . import product

print = cosmetics.print
