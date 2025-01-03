import sys
import zlib
import threading

from collections import OrderedDict

lock = threading.Lock()


class LRUCache:
    """A simple LRU cache using an OrderedDict."""

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: str) -> bytes:
        if key not in self.cache:
            return None
        else:
            with lock:
                # Move the accessed key to the end to mark it as recently used
                self.cache.move_to_end(key)
                item = self.cache[key]
                return zlib.decompress(item["blob"]) if item["compress"] else item["blob"]

    def put(self, key: str, value: bytes, compress=True):
        with lock:
            if key in self.cache:
                # Update the value of the existing key and move it to the end
                self.cache.move_to_end(key)
            self.cache[key] = {"compress": compress, "blob": zlib.compress(value) if compress else value}
            if len(self.cache) > self.capacity:
                # Remove the first item (least recently used) from the cache
                self.cache.popitem(last=False)

    def size(self) -> str:
        def get_size(obj, seen=None):
            """Recursively find the size of objects."""
            size = sys.getsizeof(obj)
            if seen is None:
                seen = set()
            obj_id = id(obj)
            if obj_id in seen:
                return 0
            seen.add(obj_id)
            if isinstance(obj, dict):
                size += sum([get_size(v, seen) for v in obj.values()])
                size += sum([get_size(k, seen) for k in obj.keys()])
            elif hasattr(obj, "__dict__"):
                size += get_size(obj.__dict__, seen)
            elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
                size += sum([get_size(i, seen) for i in obj])
            return size

        count = len(self.cache)
        s = "s" if count > 1 else ""
        total = get_size(self.cache)
        return f"{count} item{s}   {total:,d} B"
