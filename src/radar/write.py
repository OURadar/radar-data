import os
import re
import logging
import datetime
import numpy as np

from netCDF4 import Dataset

from .common import *
from .cosmetics import colorize

utc = datetime.timezone.utc
sep = colorize("/", "orange")
logger = logging.getLogger("radar-data")
dot_colors = ["black", "gray", "blue", "green", "orange"]


def write(filename, sweep):
    """
    Write a radar sweep to a netCDF file.
    """
    if not filename.endswith(".nc"):
        raise ValueError("Filename must end with .nc")

    logger.info(f"Writing {filename}...")

    # Create the directory if it does not exist
    if os.path.dirname(filename):
        os.makedirs(os.path.dirname(filename), exist_ok=True)

    with Dataset(filename, "w", format="NETCDF4") as ncid:
        _write_cf1(ncid, sweep)

    logger.info(f"Finished writing {filename}.")


def _write_cf1(ncid, sweep, string_length=32, period=20.0):
    ray_count, gate_count = sweep["elevations"].shape[0], sweep["ranges"].shape[0]
    start_datetime = datetime.datetime.fromtimestamp(sweep["time"]).replace(tzinfo=utc)
    start_timestring = start_datetime.strftime(f"%Y-%m-%dT%H:%M:%SZ")
    end_datetime = datetime.datetime.fromtimestamp(sweep.get("end_time", sweep["time"] + period)).replace(tzinfo=utc)
    end_timestring = end_datetime.strftime(f"%Y-%m-%dT%H:%M:%SZ")
    # Dimensions
    ncid.createDimension("time", ray_count)
    ncid.createDimension("range", gate_count)
    ncid.createDimension("sweep", 1)
    ncid.createDimension("string_length", string_length)
    ncid.createDimension("r_calib", 1)
    # Variables
    volume_number = ncid.createVariable("volume_number", "i4")
    volume_number.long_name = "volume_index_number_0_based"
    volume_number[:] = 0
    time_coverage_start = ncid.createVariable("time_coverage_start", "c", ("string_length",))
    time_coverage_start.standard_name = "data_volume_start_time_utc"
    time_coverage_start.comments = "ray times are relative to start time in secs"
    time_coverage_start[:] = start_timestring.ljust(string_length)
    time_coverage_end = ncid.createVariable("time_coverage_end", "c", ("string_length",))
    time_coverage_end.standard_name = "data_volume_end_time_utc"
    time_coverage_end.comments = "ray times are relative to start time in secs"
    time_coverage_end[:] = end_timestring.ljust(string_length)
    latitude = ncid.createVariable("latitude", "f8")
    latitude.standard_name = "latitude"
    latitude.units = "degrees_north"
    latitude[:] = sweep["latitude"]
    longitude = ncid.createVariable("longitude", "f8")
    longitude.standard_name = "longitude"
    longitude.units = "degrees_east"
    longitude[:] = sweep["longitude"]
    altitude = ncid.createVariable("altitude", "f8")
    altitude.units = "meters"
    altitude.standard_name = "altitude"
    altitude[:] = sweep.get("altitude", 0.0)
    sweep_number = ncid.createVariable("sweep_number", "i4", ("sweep",))
    sweep_number.long_name = "sweep_index_number_0_based"
    sweep_number[:] = 0
    sweep_mode = ncid.createVariable("sweep_mode", "c", ("sweep", "string_length"))
    sweep_mode.long_name = "scan_mode_for_sweep"
    sweep_mode[:] = "azimuth_surveillance".ljust(string_length)
    fixed_angle = ncid.createVariable("fixed_angle", "f4", ("sweep",))
    fixed_angle.long_name = "ray_target_fixed_angle"
    fixed_angle.units = "degrees"
    fixed_angle[:] = sweep["sweepElevation"]
    sweep_start_ray_index = ncid.createVariable("sweep_start_ray_index", "i4", ("sweep",))
    sweep_start_ray_index.long_name = "index_of_first_ray_in_sweep"
    sweep_start_ray_index[:] = 0
    sweep_end_ray_index = ncid.createVariable("sweep_end_ray_index", "i4", ("sweep",))
    sweep_end_ray_index.long_name = "index_of_last_ray_in_sweep"
    sweep_end_ray_index[:] = ray_count - 1

    time = ncid.createVariable("time", "f8", ("time",))
    time.standard_name = "time"
    time.long_name = "time_in_seconds_since_volume_start"
    time.units = f"seconds since {start_timestring}"
    time.calendar = "gregorian"
    time[:] = sweep.get("times", np.linspace(0, period - period / ray_count, ray_count))
    rr = ncid.createVariable("range", "f4", ("range",))
    rr.standard_name = "projection_range_coordinate"
    rr.long_name = "range_to_measurement_volume"
    rr.units = "meters"
    rr.spacing_is_constant = "true"
    rr.meters_to_center_of_first_gate = sweep["ranges"][0]
    rr.meters_between_gates = sweep["ranges"][1] - sweep["ranges"][0]
    rr.axis = "radial_range_coordinate"
    rr[:] = sweep["ranges"]
    aa = ncid.createVariable("azimuth", "f4", ("time",))
    aa.standard_name = "ray_azimuth_angle"
    aa.long_name = "azimuth_angle_from_true_north"
    aa.units = "degrees"
    aa.axis = "radial_azimuth_coordinate"
    aa[:] = sweep["azimuths"]
    ee = ncid.createVariable("elevation", "f4", ("time",))
    ee.standard_name = "ray_elevation_angle"
    ee.long_name = "elevation_angle_from_horizontal_plane"
    ee.units = "degrees"
    ee.axis = "radial_elevation_coordinate"
    ee[:] = sweep["elevations"]
    pulse_width = ncid.createVariable("pulse_width", "f4", ("time",))
    pulse_width.long_name = "transmitter_pulse_width"
    pulse_width.units = "seconds"
    pulse_width.meta_group = "instrument_parameters"
    pulse_width[:] = sweep.get("pulsewidth", 0.0001)
    prt = ncid.createVariable("prt", "f4", ("time",))
    prt.long_name = "pulse repetition time"
    prt.units = "seconds"
    prt.meta_group = "instrument_parameters"
    prt[:] = sweep.get("prt", 1.0 / sweep.get("prf", 0.001))

    products = sweep.get("products")

    def _define_and_set_data(symbol, name):
        data = products.get(symbol)
        if data is None:
            return
        if not np.ma.is_masked(data):
            data = np.ma.masked_array(data, mask=np.isnan(data))
        standard_names = {
            "Z": "equivalent_reflectivity_factor",
            "V": "radial_velocity_of_scatterers_away_from_instrument",
            "W": "doppler_spectrum_width",
            "D": "log_differential_reflectivity_hv",
            "P": "differential_phase_hv",
            "R": "cross_correlation_ratio_hv",
        }
        long_names = {
            "Z": "reflectivity",
            "V": "radial_velocity",
            "W": "spectrum_width",
            "D": "differential_reflectivity",
            "P": "differential_phase",
            "R": "cross_correlation_ratio",
        }
        units = {"Z": "dBZ", "V": "m/s", "W": "m/s", "D": "dB", "P": "degrees", "R": "unitless"}
        scale_factors = {
            "Z": np.single(0.01),
            "V": np.single(0.01),
            "W": np.single(0.01),
            "D": np.single(0.01),
            "P": np.single(0.01),
            "R": np.single(0.001),
        }
        var = ncid.createVariable(name, "i2", ("time", "range"), fill_value=-32768)
        var.standard_name = standard_names[symbol]
        var.long_name = long_names[symbol]
        var.units = units[symbol]
        var.scale_factor = scale_factors[symbol]
        var.add_offset = np.single(0.0)
        var.coordinates = "time range"
        # P should always in degrees 0-360
        if symbol == "P":
            pmax = np.max(sweep["products"]["P"])
            if pmax > 0.0 and pmax < 3.142:
                data = data * 180.0 / np.pi
        var[:] = data

    _define_and_set_data("Z", "DBZ")
    _define_and_set_data("V", "VEL")
    _define_and_set_data("W", "WIDTH")
    _define_and_set_data("D", "ZDR")
    _define_and_set_data("P", "PHIDP")
    _define_and_set_data("R", "RHOHV")

    r_calib_dbz_correction = ncid.createVariable("r_calib_dbz_correction", "f4", ("r_calib",))
    r_calib_dbz_correction.long_name = "calibrated_radar_dbz_correction"
    r_calib_dbz_correction.units = "dB"
    r_calib_dbz_correction.meta_group = "radar_calibration"
    r_calib_zdr_correction = ncid.createVariable("r_calib_zdr_correction", "f4", ("r_calib",))
    r_calib_zdr_correction.long_name = "calibrated_radar_zdr_correction"
    r_calib_zdr_correction.units = "dB"
    r_calib_zdr_correction.meta_group = "radar_calibration"
    r_calib_system_phidp = ncid.createVariable("r_calib_system_phidp", "f4", ("r_calib",))
    r_calib_system_phidp.long_name = "calibrated_radar_system_phidp"
    r_calib_system_phidp.units = "degrees"
    r_calib_system_phidp.meta_group = "radar_calibration"

    # Global attributes
    ncid.Conventions = "CF-1.7"
    ncid.Sub_conventions = "CF-Radial instrument_parameters radar_calibration"
    ncid.version = "CF-Radial-1.4"
    ncid.title = "Radar products"
    ncid.institution = "University of Oklahoma"
    ncid.source = "radar observation"
    ncid.history = ""
    ncid.references = ""
    ncid.comment = f"Radar Data"
    ncid.instrument_name = ""
    ncid.time_coverage_start = start_timestring
    ncid.time_coverage_end = end_timestring
    ncid.start_datetime = start_timestring
    ncid.end_datetime = end_timestring
    ncid.created = datetime.datetime.now(utc).strftime(f"%Y-%m-%dT%H:%M:%SZ")
    ncid.platform_is_mobile = "false"
    ncid.ray_times_increase = "true"
