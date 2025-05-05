import os
import re
import logging
import tarfile
import datetime
import numpy as np

from netCDF4 import Dataset

from .common import *
from .cosmetics import colorize
from .nexrad import get_nexrad_location, get_vcp_msg31_timestamp, is_nexrad_format

utc = datetime.timezone.utc
sep = colorize("/", "orange")
logger = logging.getLogger("radar-data")
dot_colors = ["black", "gray", "blue", "green", "orange"]

np.set_printoptions(precision=2, suppress=True, threshold=10)

EPOCH_DATETIME_UTC = datetime.datetime(1970, 1, 1, tzinfo=utc)


class Kind:
    UNK = "U"
    CF1 = "1"
    CF2 = "2"
    M31 = "31"
    WDS = "W"


class TxRx:
    BISTATIC = "B"
    MONOSTATIC = "M"


"""
    Value to index conversion using RadarKit convention
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


def _read_ncid(ncid, symbols={"Z", "V", "W", "D", "P", "R"}, verbose=0):
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
        if verbose > 1:
            logger.debug(f"{myname} {version} {sep} {conventions} {sep} {subConventions}")
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
        if verbose > 1:
            createdBy = ncid.getncattr("CreatedBy")
            logger.debug(f"{myname} WDSS-II {sep} {createdBy}")
        return _read_wds_from_ncid(ncid)
    else:
        raise ValueError(f"{myname} Unidentified NetCDF format")


def _get_variable_as_masked_float32(variables, name):
    variable = variables[name][:]
    return np.ma.array(variable.data, mask=variable.mask, dtype=np.float32, fill_value=np.nan)


def _read_cf1_from_ncid(ncid, symbols={"Z", "V", "W", "D", "P", "R"}):
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
        timestamp = datetime.datetime.fromisoformat(timeString).replace(tzinfo=utc).timestamp()
    except Exception as e:
        raise ValueError(f"Unexpected timeString = {timeString}   e = {e}")
    sweepElevation = 0.0
    sweepAzimuth = 0.0
    variables = ncid.variables
    elevations = np.array(variables["elevation"][:], dtype=np.float32)
    azimuths = np.array(variables["azimuth"][:], dtype=np.float32)
    mode = b"".join(variables["sweep_mode"][:]).decode("utf-8", errors="ignore").rstrip(" \x00")
    if mode == "azimuth_surveillance":
        sweepElevation = float(variables["fixed_angle"][:])
    elif mode == "rhi":
        sweepAzimuth = float(variables["fixed_angle"][:])
    products = {}
    if "Z" in symbols:
        if "DBZ" in variables:
            products["Z"] = _get_variable_as_masked_float32(variables, "DBZ")
        elif "DBZHC" in variables:
            products["Z"] = _get_variable_as_masked_float32(variables, "DBZHC")
    if "V" in symbols:
        if "VEL" in variables:
            products["V"] = _get_variable_as_masked_float32(variables, "VEL")
        elif "VR" in variables:
            products["V"] = _get_variable_as_masked_float32(variables, "VR")
    if "W" in symbols and "WIDTH" in variables:
        products["W"] = _get_variable_as_masked_float32(variables, "WIDTH")
    if "D" in symbols and "ZDR" in variables:
        products["D"] = _get_variable_as_masked_float32(variables, "ZDR")
    if "P" in symbols and "PHIDP" in variables:
        products["P"] = _get_variable_as_masked_float32(variables, "PHIDP")
    if "R" in symbols and "RHOHV" in variables:
        products["R"] = _get_variable_as_masked_float32(variables, "RHOHV")
    prf = "-"
    waveform = "u"
    gatewidth = 100.0
    if "prt" in variables:
        prf = round(1.0 / variables["prt"][:][0], 1)
    if "radarkit_parameters" in ncid.groups:
        group = ncid.groups["radarkit_parameters"]
        attrs = group.ncattrs()
        if "waveform" in attrs:
            waveform = group.getncattr("waveform")
        if "prt" in attrs:
            prf = round(float(group.getncattr("prf")), 1)
    if "meters_between_gates" in variables["range"]:
        gatewidth = float(variables["range"].getncattr("meters_between_gates"))
    else:
        ranges = np.array(variables["range"][:2], dtype=float)
        gatewidth = ranges[1] - ranges[0]
    ranges = np.array(variables["range"][:], dtype=np.float32)
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
def _read_cf2_from_ncid(ncid, symbols={"Z", "V", "W", "D", "P", "R"}):
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
        timestamp = datetime.datetime.fromisoformat(timeString).replace(tzinfo=utc).timestamp()
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
            products["Z"] = _get_variable_as_masked_float32(variables, "DBZ")
        elif "RCP" in variables:
            products["Z"] = _get_variable_as_masked_float32(variables, "RCP")
    if "V" in symbols and "VEL" in variables:
        products["V"] = _get_variable_as_masked_float32(variables, "VEL")
    if "W" in symbols and "WIDTH" in variables:
        products["W"] = _get_variable_as_masked_float32(variables, "WIDTH")
    if "D" in symbols and "ZDR" in variables:
        products["D"] = _get_variable_as_masked_float32(variables, "ZDR")
    if "P" in symbols and "PHIDP" in variables:
        products["P"] = _get_variable_as_masked_float32(variables, "PHIDP")
    if "R" in symbols and "RHOHV" in variables:
        products["R"] = _get_variable_as_masked_float32(variables, "RHOHV")
    return {
        "kind": Kind.CF2,
        "txrx": TxRx.BISTATIC,
        "time": timestamp,
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
    variables = ncid.variables
    elevations = np.array(variables["Elevation"][:], dtype=np.float32)
    azimuths = np.array(variables["Azimuth"][:], dtype=np.float32)
    if "GateSize" in attrs:
        r0, nr, dr = ncid.getncattr("RangeToFirstGate"), ncid.dimensions["Gate"].size, ncid.getncattr("GateSize")
    elif "GateWidth" in variables:
        r0, nr, dr = ncid.getncattr("RangeToFirstGate"), ncid.dimensions["Gate"].size, variables["GateWidth"][:][0]
    else:
        logger.warning(f"Missing GateSize or GateWidth in {name}")
        r0, nr, dr = 0.0, ncid.dimensions["Gate"].size, 1.0
    ranges = r0 + np.arange(nr, dtype=np.float32) * dr
    values = np.array(variables[name][:], dtype=np.float32)
    values[values < -90] = np.nan
    scantime = EPOCH_DATETIME_UTC + datetime.timedelta(seconds=int(ncid.getncattr("Time")))
    timestamp = scantime.timestamp()
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
        "time": timestamp,
        "latitude": float(ncid.getncattr("Latitude")),
        "longitude": float(ncid.getncattr("Longitude")),
        "sweepElevation": ncid.getncattr("Elevation") if "Elevation" in attrs else 0.0,
        "sweepAzimuth": ncid.getncattr("Azimuth") if "Azimuth" in attrs else 0.0,
        "prf": float(round(ncid.getncattr("PRF-value") * 0.1) * 10.0),
        "waveform": ncid.getncattr("Waveform") if "Waveform" in attrs else "",
        "gatewidth": dr,
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


def _read_tar(source, symbols={"Z", "V", "W", "D", "P", "R"}, tarinfo=None, want_tarinfo=False, verbose=0):
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
            with Dataset("memory", memory=content) as ncid:
                sweep = _read_ncid(ncid, symbols=symbols, verbose=verbose)
        else:
            for symbol in symbols & set(tarinfo):
                info = _quartet_to_tarinfo(tarinfo[symbol])
                with aid.extractfile(info) as fid:
                    if verbose > 1:
                        show = colorize(info.name, "yellow")
                        logger.debug(f"{myname} {show}")
                    content = fid.read()
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


def _read_nc(source, symbols={"Z", "V", "W", "D", "P", "R"}, verbose=0):
    myname = colorize("radar._read_nc()", "green")
    basename = os.path.basename(source)
    parts = re_4parts.search(basename)
    if parts is None:
        parts = re_3parts.search(basename)
        if parts is None:
            with Dataset(source, mode="r") as ncid:
                return _read_ncid(ncid, symbols=symbols, verbose=verbose)
    parts = parts.groupdict()
    if verbose > 1:
        logger.debug(f"{myname} parts = {parts}")
    if "symbol" not in parts:
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
        with Dataset(source, mode="r") as ncid:
            return _read_ncid(ncid, symbols=symbols, verbose=verbose)
    sweep = None
    for file in files:
        if verbose > 1:
            show = colorize(os.path.basename(file), "yellow")
            logger.debug(f"{myname} {show}")
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


def _read_nexrad(source, sweep_index=0, symbols={"Z", "V", "W", "D", "P", "R"}, verbose=0):
    if verbose > 1:
        myname = colorize("radar._read_nexrad()", "green")
        logger.debug(f"{myname} {colorize(source, 'yellow')}")

    vcp, msg31, timestamp = get_vcp_msg31_timestamp(source, sweep_index=sweep_index, verbose=verbose)

    nrays = len(msg31)
    data = msg31[0].data
    products = {"REF", "VEL", "SW", "ZDR", "PHI", "RHO"} & set(data.keys())
    max_gates = min([data[p].ngates for p in products])
    r0 = data["REF"].r0
    dr = data["REF"].dr
    rr = np.arange(r0, r0 + max_gates * dr, dr)
    ee = np.zeros(nrays, ">f4")
    aa = np.zeros(nrays, ">f4")
    days = np.zeros(nrays, ">i4")
    secs = np.zeros(nrays, ">i4")
    for k, msg in enumerate(msg31):
        data_header = msg.head
        ee[k] = data_header.elevation_angle
        aa[k] = data_header.azimuth_angle
        days[k] = data_header.timestamp
        secs[k] = data_header.timestamp_ms
    # Assemble the products
    arrays = {}
    for symbol in products:
        ngates = data[symbol].ngates
        values = np.zeros((nrays, ngates), dtype="H" if data[symbol].word_size == 16 else "B")
        offset = np.float32(data[symbol].offset)
        scale = np.float32(data[symbol].scale)
        for k, msg in enumerate(msg31):
            values[k, :] = msg.data[symbol].values
        mask = values <= 1
        values = (values - offset) / scale
        arrays[symbol] = np.ma.array(values[:, :max_gates], mask=mask[:, :max_gates], fill_value=np.nan)
    # Replace keys: REF -> Z, VEL -> V, SW -> W, ZDR -> D, PHI -> P, RHO -> R
    products = {}
    if "REF" in arrays and "Z" in symbols:
        products["Z"] = arrays["REF"]
    if "VEL" in arrays and "V" in symbols:
        products["V"] = arrays["VEL"]
    if "SW" in arrays and "W" in symbols:
        products["W"] = arrays["SW"]
    if "ZDR" in arrays and "D" in symbols:
        products["D"] = arrays["ZDR"]
    if "PHI" in arrays and "P" in symbols:
        products["P"] = arrays["PHI"]
    if "RHO" in arrays and "R" in symbols:
        products["R"] = arrays["RHO"]
    return {
        "kind": Kind.M31,
        "txrx": TxRx.MONOSTATIC,
        "time": timestamp,
        "latitude": data["VOL"].latitude,
        "longitude": data["VOL"].longitude,
        "sweepElevation": vcp.data[sweep_index].elevation_angle,
        "sweepAzimuth": 0.0,
        "prf": msg31[0].prf,
        "waveform": "u",
        "gatewidth": data["REF"].dr,
        "elevations": ee,
        "azimuths": aa,
        "ranges": rr,
        "products": products,
    }


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
    symbols: list of str, default = {"Z", "V", "W", "D", "P", "R"}
    finite: bool - Convert NaN to 0, default = False
    tarinfo: dict - Tarball information, default = None
    want_tarinfo: bool - Return tarinfo, default = False
    u8: bool - Convert values to uint8, default = False
    """
    verbose = kwargs.get("verbose", 0)
    symbols = kwargs.get("symbols", {"Z", "V", "W", "D", "P", "R"})
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
    elif is_nexrad_format(source):
        sweep_index = kwargs.get("sweep_index", 0)
        data = _read_nexrad(source, sweep_index=sweep_index, symbols=symbols, verbose=verbose)
        tarinfo = {}
    else:
        raise ValueError(f"{myname} Unsupported file format (ext = {ext})")
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


def set_logger(new_logger):
    global logger
    logger = new_logger
