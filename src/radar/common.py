import re

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

class Kind:
    UNK = "U"
    CF1 = "1"
    CF2 = "2"
    M31 = "31"
    WDS = "W"


class TxRx:
    BISTATIC = "B"
    MONOSTATIC = "M"
