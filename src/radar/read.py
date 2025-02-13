import os
import re
import logging
import tarfile
import datetime
import threading
import numpy as np

from netCDF4 import Dataset

from .common import *
from .cosmetics import colorize, NumpyPrettyPrinter
from .dailylog import Logger
from .nexrad import get_nexrad_location

_lock = threading.Lock()

np.set_printoptions(precision=2, suppress=True, threshold=10)

sep = colorize("/", "orange")
dot_colors = ["black", "gray", "blue", "green", "orange"]
sweep_printer = NumpyPrettyPrinter(depth=2, indent=2, sort_dicts=False)
tzinfo = datetime.timezone.utc
logger = Logger("radar-data")


class Kind:
    UNK = "U"
    CF1 = "1"
    CF2 = "2"
    WDS = "W"


class TxRx:
    BISTATIC = "B"
    MONOSTATIC = "M"


"""
    value - Raw values
"""


def val2ind(v, symbol="Z"):
    def rho2ind(x):
        m3 = x > 0.93
        m2 = np.logical_and(x > 0.7, ~m3)
        index = x * 52.8751
        index[m2] = x[m2] * 300.0 - 173.0
        index[m3] = x[m3] * 1000.0 - 824.0
        return index

    if symbol == "Z":
        u8 = v * 2.0 + 64.0
    elif symbol == "V":
        u8 = v * 2.0 + 128.0
    elif symbol == "W":
        u8 = v * 20.0
    elif symbol == "D":
        u8 = v * 10.0 + 100.0
    elif symbol == "P":
        u8 = v * 128.0 / 180.0 + 128.0
    elif symbol == "R":
        u8 = rho2ind(v)
    elif symbol == "I":
        u8 = (v - 0.5) * 42 + 46
    else:
        u8 = v
    # Map to closest integer, 0 is transparent, 1+ is finite.
    # np.nan will be converted to 0 during np.nan_to_num(...)
    return np.nan_to_num(np.clip(np.round(u8), 1.0, 255.0), copy=False).astype(np.uint8)


def _starts_with_cf(string):
    return bool(re.match(r"^cf", string, re.IGNORECASE))


def _read_ncid(ncid, symbols=["Z", "V", "W", "D", "P", "R"], verbose=0):
    myname = colorize("radar._read_ncid()", "green")
    attrs = ncid.ncattrs()
    if verbose > 2:
        logger.debug(attrs)
    # CF-Radial format contains "Conventions" and "version"
    if "Conventions" in attrs and _starts_with_cf(ncid.getncattr("Conventions")):
        conventions = ncid.getncattr("Conventions")
        subConventions = ncid.getncattr("Sub_conventions") if "Sub_conventions" in attrs else None
        version = ncid.getncattr("version") if "version" in attrs else None
        if version is None:
            raise ValueError(f"{myname} No version found")
        if verbose:
            logger.info(f"{myname} {version} {sep} {conventions} {sep} {subConventions}")
        m = re_cf_version.match(version)
        if m:
            m = m.groupdict()
            versionNumber = m["version"]
            if versionNumber >= "2.0":
                return _read_cf2_from_ncid(ncid, symbols=symbols)
            return _read_cf1_from_ncid(ncid, symbols=symbols)
        elif version >= "2":
            return _read_cf2_from_ncid(ncid, symbols=symbols)
        elif version[0] == "1":
            return _read_cf1_from_ncid(ncid, symbols=symbols)
        show = f"{myname} {version} {sep} {conventions} {sep} {subConventions}"
        raise ValueError(f"{myname} Unsupported format {show}")
    # WDSS-II format contains "TypeName" and "DataType"
    elif "TypeName" in attrs and "DataType" in attrs:
        if verbose:
            createdBy = ncid.getncattr("CreatedBy")
            logger.info(f"{myname} WDSS-II {sep} {createdBy}")
        return _read_wds_from_ncid(ncid)
    else:
        raise ValueError(f"{myname} Unidentified NetCDF format")


def _read_cf1_from_ncid(ncid, symbols=["Z", "V", "W", "D", "P", "R"]):
    longitude = float(ncid.variables["longitude"][0])
    latitude = float(ncid.variables["latitude"][0])
    attrs = ncid.ncattrs()
    if "time_coverage_start" in attrs:
        timeString = ncid.getncattr("time_coverage_start")
    elif "time_coverage_start" in ncid.variables:
        timeString = b"".join(ncid.variables["time_coverage_start"][:]).decode("utf-8", errors="ignore").rstrip(" \x00")
    else:
        raise ValueError("No time_coverage_start")
    if timeString.endswith(r"Z"):
        timeString = timeString[:-1]
    try:
        timestamp = datetime.datetime.fromisoformat(timeString).replace(tzinfo=tzinfo).timestamp()
    except Exception as e:
        raise ValueError(f"Unexpected timeString = {timeString}   e = {e}")
    # if "sweep_number" in ncid.variables:
    #     sweepNumber = ncid.variables["sweep_number"][:]
    #     # print(f"sweepNumber = {sweepNumber}")
    sweepElevation = 0.0
    sweepAzimuth = 0.0
    elevations = np.array(ncid.variables["elevation"][:], dtype=np.float32)
    azimuths = np.array(ncid.variables["azimuth"][:], dtype=np.float32)
    mode = b"".join(ncid.variables["sweep_mode"][:]).decode("utf-8", errors="ignore").rstrip(" \x00")
    if mode == "azimuth_surveillance":
        sweepElevation = float(ncid.variables["fixed_angle"][:])
    elif mode == "rhi":
        sweepAzimuth = float(ncid.variables["fixed_angle"][:])
    products = {}
    if "Z" in symbols:
        if "DBZ" in ncid.variables:
            products["Z"] = ncid.variables["DBZ"][:]
        elif "DBZHC" in ncid.variables:
            products["Z"] = ncid.variables["DBZHC"][:]
    if "V" in symbols and "VEL" in ncid.variables:
        products["V"] = ncid.variables["VEL"][:]
    elif "V" in symbols and "VR" in ncid.variables:
        products["V"] = ncid.variables["VR"][:]
    if "W" in symbols and "WIDTH" in ncid.variables:
        products["W"] = ncid.variables["WIDTH"][:]
    if "D" in symbols and "ZDR" in ncid.variables:
        products["D"] = ncid.variables["ZDR"][:]
    if "P" in symbols and "PHIDP" in ncid.variables:
        products["P"] = ncid.variables["PHIDP"][:]
    if "R" in symbols and "RHOHV" in ncid.variables:
        products["R"] = ncid.variables["RHOHV"][:]
    prf = "-"
    waveform = "u"
    gatewidth = 100.0
    if "prt" in ncid.variables:
        prf = round(1.0 / ncid.variables["prt"][:][0], 1)
    if "radarkit_parameters" in ncid.groups:
        group = ncid.groups["radarkit_parameters"]
        attrs = group.ncattrs()
        if "waveform" in attrs:
            waveform = group.getncattr("waveform")
        if "prt" in attrs:
            prf = round(float(group.getncattr("prf")), 1)
    if "meters_between_gates" in ncid.variables["range"]:
        gatewidth = float(ncid.variables["range"].getncattr("meters_between_gates"))
    else:
        ranges = np.array(ncid.variables["range"][:2], dtype=float)
        gatewidth = ranges[1] - ranges[0]
    ranges = np.array(ncid.variables["range"][:], dtype=np.float32)
    return {
        "kind": Kind.CF1,
        "txrx": TxRx.MONOSTATIC,
        "time": timestamp,
        "latitude": latitude,
        "longitude": longitude,
        "sweepElevation": sweepElevation,
        "sweepAzimuth": sweepAzimuth,
        "prf": prf,
        "waveform": waveform,
        "gatewidth": gatewidth,
        "elevations": elevations,
        "azimuths": azimuths,
        "ranges": ranges,
        "products": products,
    }


# TODO: Need to make this more generic
def _read_cf2_from_ncid(ncid, symbols=["Z", "V", "W", "D", "P", "R"]):
    site = ncid.getncattr("instrument_name")
    location = get_nexrad_location(site)
    if location:
        longitude = location["longitude"]
        latitude = location["latitude"]
    else:
        longitude = ncid.variables["longitude"][:]
        latitude = ncid.variables["latitude"][:]
    timeString = ncid.getncattr("start_time")
    if timeString.endswith("Z"):
        timeString = timeString[:-1]
    try:
        time = datetime.datetime.fromisoformat(timeString).replace(tzinfo=tzinfo).timestamp()
    except Exception as e:
        raise ValueError(f"Unexpected timeString = {timeString} {e}")
    variables = ncid.groups["sweep_0001"].variables
    sweepMode = variables["sweep_mode"][:]
    fixedAngle = float(variables["fixed_angle"][:])
    sweepElevation, sweepAzimuth = 0.0, 0.0
    if sweepMode == "azimuth_surveillance":
        sweepElevation = fixedAngle
    elif sweepMode == "rhi":
        sweepAzimuth = fixedAngle
    elevations = np.array(variables["elevation"][:], dtype=np.float32)
    azimuths = np.array(variables["azimuth"][:], dtype=np.float32)
    ranges = np.array(variables["range"][:], dtype=np.float32)
    products = {}
    if "Z" in symbols:
        if "DBZ" in variables:
            products["Z"] = variables["DBZ"][:]
        elif "RCP" in variables:
            products["Z"] = variables["RCP"][:]
    if "V" in symbols and "VEL" in variables:
        products["V"] = variables["VEL"][:]
    if "W" in symbols and "WIDTH" in variables:
        products["W"] = variables["WIDTH"][:]
    if "D" in symbols and "ZDR" in variables:
        products["D"] = variables["ZDR"][:]
    if "P" in symbols and "PHIDP" in variables:
        products["P"] = variables["PHIDP"][:]
    if "R" in symbols and "RHOHV" in variables:
        products["R"] = variables["RHOHV"][:]
    return {
        "kind": Kind.CF2,
        "txrx": TxRx.BISTATIC,
        "time": time,
        "latitude": latitude,
        "longitude": longitude,
        "sweepElevation": sweepElevation,
        "sweepAzimuth": sweepAzimuth,
        "rxOffsetX": -14.4867,
        "rxOffsetY": -16.8781,
        "rxOffsetZ": -0.03878,
        "prf": 1000.0,
        "waveform": "u",
        "gatewidth": 400.0,
        "elevations": elevations,
        "azimuths": azimuths,
        "ranges": ranges,
        "products": products,
    }


def _read_wds_from_ncid(ncid):
    name = ncid.getncattr("TypeName")
    attrs = ncid.ncattrs()
    elevations = np.array(ncid.variables["Elevation"][:], dtype=np.float32)
    azimuths = np.array(ncid.variables["Azimuth"][:], dtype=np.float32)
    if "GateSize" in attrs:
        r0, nr, dr = ncid.getncattr("RangeToFirstGate"), ncid.dimensions["Gate"].size, ncid.getncattr("GateSize")
    elif "GateWidth" in ncid.variables:
        r0, nr, dr = ncid.getncattr("RangeToFirstGate"), ncid.dimensions["Gate"].size, ncid.variables["GateWidth"][:][0]
    ranges = r0 + np.arange(nr, dtype=np.float32) * dr
    values = np.array(ncid.variables[name][:], dtype=np.float32)
    values[values < -90] = np.nan
    if name == "RhoHV":
        symbol = "R"
    elif name == "PhiDP":
        symbol = "P"
    elif name == "Differential_Reflectivity":
        symbol = "D"
    elif name == "Width":
        symbol = "W"
    elif name == "Radial_Velocity" or name == "Velocity":
        symbol = "V"
    elif name == "Intensity" or name == "Corrected_Intensity" or name == "Reflectivity":
        symbol = "Z"
    else:
        symbol = "U"
    return {
        "kind": Kind.WDS,
        "txrx": TxRx.MONOSTATIC,
        "time": ncid.getncattr("Time"),
        "latitude": float(ncid.getncattr("Latitude")),
        "longitude": float(ncid.getncattr("Longitude")),
        "sweepElevation": ncid.getncattr("Elevation") if "Elevation" in attrs else 0.0,
        "sweepAzimuth": ncid.getncattr("Azimuth") if "Azimuth" in attrs else 0.0,
        "prf": float(round(ncid.getncattr("PRF-value") * 0.1) * 10.0),
        "waveform": ncid.getncattr("Waveform") if "Waveform" in attrs else "",
        "gatewidth": float(ncid.variables["GateWidth"][:][0]),
        "createdBy": ncid.getncattr("CreatedBy"),
        "elevations": elevations,
        "azimuths": azimuths,
        "ranges": ranges,
        "products": {symbol: values},
    }


def _quartet_to_tarinfo(quartet):
    info = tarfile.TarInfo(quartet[0])
    info.size = quartet[1]
    info.offset = quartet[2]
    info.offset_data = quartet[3]
    return info


def _read_tar(source, symbols=["Z", "V", "W", "D", "P", "R"], tarinfo=None, want_tarinfo=False, verbose=0):
    myname = colorize("radar._read_tar()", "green")
    if tarinfo is None:
        tarinfo = read_tarinfo(source, verbose=verbose)
    show = colorize(source, "yellow")
    if not tarinfo:
        logger.error(f"{myname} Unable to retrieve tarinfo in {show}")
        return (None, tarinfo) if want_tarinfo else None
    elif verbose > 1:
        logger.debug(f"{myname} {show}")
    sweep = None
    with tarfile.open(source) as aid:
        if "*" in tarinfo:
            info = _quartet_to_tarinfo(tarinfo["*"])
            with aid.extractfile(info) as fid:
                content = fid.read()
                with _lock:
                    with Dataset("memory", memory=content) as ncid:
                        sweep = _read_ncid(ncid, symbols=symbols, verbose=verbose)
        else:
            for symbol in symbols:
                if symbol not in tarinfo:
                    continue
                info = _quartet_to_tarinfo(tarinfo[symbol])
                with aid.extractfile(info) as fid:
                    if verbose > 1:
                        show = colorize(info.name, "yellow")
                        logger.debug(f"{myname} {show}")
                    content = fid.read()
                    with _lock:
                        with Dataset("memory", mode="r", memory=content) as ncid:
                            single = _read_ncid(ncid, symbols=symbols, verbose=verbose)
                    if sweep is None:
                        sweep = single
                    else:
                        sweep["products"] = {**sweep["products"], **single["products"]}
    if sweep is None:
        logger.error(f"{myname} No sweep found in {source}")
        return (None, tarinfo) if want_tarinfo else None
    if sweep["sweepElevation"] == 0.0 and sweep["sweepAzimuth"] == 0.0:
        basename = os.path.basename(source)
        parts = re_3parts.search(basename).groupdict()
        if parts["scan"][0] == "E":
            sweep["sweepElevation"] = float(parts["scan"][1:])
        elif parts["scan"][0] == "A":
            sweep["sweepAzimuth"] = float(parts["scan"][1:])
    return (sweep, tarinfo) if want_tarinfo else sweep


def _read_nc(source, symbols=["Z", "V", "W", "D", "P", "R"], verbose=0):
    myname = colorize("radar._read_nc()", "green")
    basename = os.path.basename(source)
    parts = re_4parts.search(basename)
    if parts is None:
        parts = re_3parts.search(basename)
        if parts is None:
            with _lock:
                with Dataset(source, mode="r") as ncid:
                    return _read_ncid(ncid, symbols=symbols, verbose=verbose)
    parts = parts.groupdict()
    if verbose > 1:
        logger.debug(f"{myname} parts = {parts}")
    if "symbol" not in parts:
        with _lock:
            with Dataset(source, mode="r") as ncid:
                return _read_ncid(ncid, symbols=symbols, verbose=verbose)
    folder = os.path.dirname(source)
    known = True
    files = []
    for symbol in symbols:
        basename = "-".join([parts["name"], parts["time"], parts["scan"], symbol]) + ".nc"
        path = os.path.join(folder, basename)
        if not os.path.exists(path):
            known = False
            break
        files.append(path)
    if not known:
        if verbose > 1:
            logger.debug(f"{myname} {source}")
        with _lock:
            with Dataset(source, mode="r") as ncid:
                return _read_ncid(ncid, symbols=symbols, verbose=verbose)
    sweep = None
    for file in files:
        if verbose > 1:
            show = colorize(os.path.basename(file), "yellow")
            logger.debug(f"{myname} {show}")
        with _lock:
            with Dataset(file, mode="r") as ncid:
                single = _read_ncid(ncid, symbols=symbols, verbose=verbose)
        if single is None:
            logger.error(f"{myname} Unexpected {file}")
            return None
        if sweep is None:
            sweep = single
        else:
            sweep["products"] = {**sweep["products"], **single["products"]}
    return sweep


def read_tarinfo(source, verbose=0):
    tarinfo = {}
    try:
        with tarfile.open(source) as aid:
            members = aid.getmembers()
            members = [m for m in members if m.isfile() and not os.path.basename(m.name).startswith(".")]
            if verbose > 1:
                myname = colorize("radar.read_tarinfo()", "green")
                logger.debug(f"{myname} {members}")
            tarinfo = {}
            if len(members) == 1:
                m = members[0]
                tarinfo["*"] = [m.name, m.size, m.offset, m.offset_data]
            else:
                for m in members:
                    parts = re_4parts.search(os.path.basename(m.name)).groupdict()
                    tarinfo[parts["symbol"]] = [m.name, m.size, m.offset, m.offset_data]
    except tarfile.ReadError:
        logger.error(f"Error: The archive {source} is not a valid tar file")
    except tarfile.ExtractError:
        logger.error(f"Error: An error occurred while extracting the archive {source}")
    except Exception as e:
        logger.error(f"Error: {e}")
    return tarinfo


def read(source, **kwargs):
    """
    read(source, **kwargs):

    Read radar data from a file or a tarball.

    Parameters:
    source: str - Path to a file or a tarball.

    Optional keyword arguments:
    verbose: int - Verbosity level, default = 0
    symbols: list of str, default = ["Z", "V", "W", "D", "P", "R"]
    finite: bool - Convert NaN to 0, default = False
    tarinfo: dict - Tarball information, default = None
    want_tarinfo: bool - Return tarinfo, default = False
    u8: bool - Convert values to uint8, default = False
    """
    verbose = kwargs.get("verbose", 0)
    symbols = kwargs.get("symbols", ["Z", "V", "W", "D", "P", "R"])
    finite = kwargs.get("finite", False)
    tarinfo = kwargs.get("tarinfo", None)
    want_tarinfo = kwargs.get("want_tarinfo", False)
    #
    myname = colorize("radar.read()", "green")
    if verbose:
        logger.setLevel(logging.DEBUG if verbose > 1 else logging.INFO)
        show = colorize(source, "yellow")
        logger.info(f"{myname} {show}")
    if not os.path.exists(source):
        raise FileNotFoundError(f"{myname} {source} not found")
    ext = os.path.splitext(source)[1]
    if ext in [".txz", ".xz", ".tgz", ".tar"]:
        output = _read_tar(
            source,
            verbose=verbose,
            symbols=symbols,
            tarinfo=tarinfo,
            want_tarinfo=want_tarinfo,
        )
        if want_tarinfo:
            data, tarinfo = output
        else:
            data = output
    elif ext == ".nc":
        data = _read_nc(source, symbols=symbols, verbose=verbose)
        tarinfo = {}
    else:
        raise ValueError(f"{myname} Unsupported file extension {ext}")
    if data is None:
        raise ValueError(f"{myname} No data found in {source}")
    if kwargs.get("u8", False):
        data["u8"] = {}
        for key, value in data["products"].items():
            if np.ma.isMaskedArray(value):
                value = value.filled(np.nan)
            data["u8"][key] = val2ind(value, symbol=key)
    if finite:
        for key, value in data["products"].items():
            data["products"][key] = np.nan_to_num(value)
    if want_tarinfo:
        return data, tarinfo
    return data


def pprint(obj):
    return sweep_printer.pprint(obj)


def set_logger(new_logger):
    global logger
    logger = new_logger
