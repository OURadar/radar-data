import re
import numpy as np

re_2parts = re.compile(
    r"(?P<name>.+)[._-](?P<time>20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d)[._-]"
)
re_3parts = re.compile(
    r"(?P<name>.+)[._-]"
    + r"(?P<time>20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d)[._-]"
    + r"(?P<scan>([EAN]\d+\.\d|N\d+))"
)
re_4parts = re.compile(
    r"(?P<name>.+)[._-]"
    + r"(?P<time>20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d)[._-]"
    + r"(?P<scan>([EAN]\d+\.\d|N\d+))[._-]"
    + r"(?P<symbol>[A-Za-z0-9]+)"
)
re_cf_version = re.compile(r"(CF|Cf|cf).+-(?P<version>[0-9]+\.[0-9]+)")
re_datetime_a = re.compile(r"(?<=[._-])20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d\.\d+")
re_datetime_b = re.compile(r"(?<=[._-])20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d")
re_datetime_f = re.compile(r"20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d.\d+")
re_datetime_s = re.compile(r"20\d{2}(0\d|1[012])([012]\d|3[01])[._-]([01]\d|2[0-3])[0-5]\d[0-5]\d")

empty_sweep = {
    "kind": "U",
    "txrx": "M",
    "symbol": "U",
    "time": 1369071296.0,
    "latitude": 35.25527,
    "longitude": -97.422413,
    "sweepElevation": 0.5,
    "sweepAzimuth": 42.0,
    "gatewidth": 15.0,
    "waveform": "s0",
    "prf": 1000.0,
    "elevations": np.empty((0, 0), dtype=np.float32),
    "azimuths": np.empty((0, 0), dtype=np.float32),
    "values": {"U": np.empty((0, 0), dtype=np.float32)},
    "u8": {"U": np.empty((0, 0), dtype=np.uint8)},
}
