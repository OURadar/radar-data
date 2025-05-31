"""
-------------------------------------------------------------------------
                           Volume Header Record
A 24-byte record that is described in Figure 1. This record will contain
the volume number along with a date and time field.
.........................................................................
                          LDM Compressed Record
A record that is bzip2 compressed. It consists of Metadata message types
15, 13, 18, 3, 5, and 2. See section 7.3.5.

                 (These two records are in the *-S file)
-------------------------------------------------------------------------
                          LDM Compressed Record
A variable size record that is bzip2 compressed. It consists of 120 radial
data messages (type 1 or 31) plus 0 or more RDA Status messages (type
2). The last message will have a radial status signaling "end of
elevation" or "end of volume". See paragraph 7.3.4.
                     (This record is in a -I file)
-------------------------------------------------------------------------
                      Repeat (LDM Compressed Record)
                                  Or
                   End of File (for end of volume data)

                      (This record is in a *-I file)
                      (Last record is in a *-E file)
--------------------------------------------------------------------------

Modified from Figure 2 in NEXRAD Interface Control Document 2620010E
"""

import os
import re
import bz2
import glob
import json
import struct
import logging
import datetime
import urllib.request
import numpy as np

from .cosmetics import colorize

# The first 12 bytes are empty, which means the "Message Size" does not begin until byte 13
EMPTY_BYTE_COUNT = 12

# A 24-byte record that is described in Figure 1
VOLUME_HEADER_SIZE = 24

# The structure of the LDM Compressed Record is a 4-byte, big-endian, signed binary control word
LDM_CONTROL_WORD_SIZE = 4

# It contains the number of 2432 byte message segments set aside for each message type ...
METADATA_RECORD_SIZE = 2432

# The size of the uncompressed metadata is fixed at 134 messages, ie. 325888 bytes
# Message Type 15, 77 segments
# Message Type 13, 49 segments
# Message Type 18, 5 segment
# Message Type 3, 1 segment
# Message Type 5, 1 segment
# Message Type 2, 1 segment
META_DATA_SIZE = 325888
MESSAGE_5_OFFSET = EMPTY_BYTE_COUNT + META_DATA_SIZE - 2 * METADATA_RECORD_SIZE

# Metadata Record is a variable number of compressed records containing 120 radial messages (type 31)
RADIALS_PER_RECORD = 120

# The wavelength of the NEXRAD radar signal in meters
NEXRAD_WAVELENGTH = 0.10

# Find the blob directory to retrieve NEXRAD locations
FILE_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.dirname(FILE_DIR)
BLOB_DIR = os.path.join(BASE_DIR, "blob")
if not os.path.exists(BLOB_DIR):
    os.mkdir(BLOB_DIR)
NEXRAD_DB = os.path.join(BLOB_DIR, "nexrad-locations.json")
NEXRAD = {}

# Look for something like KTLX-20250426-121335-999-13-I
re_parts_stripped = re.compile(
    r".*(?P<icao>K[A-Z]{3})-"
    + r"(?P<time>20\d{2}(0\d|1[012])([012]\d|3[01])-([01]\d|2[0-3])[0-5]\d[0-5]\d)-"
    + r"(?P<scan>\d+)-"
    + r"(?P<part>\d+)-"
    + r"(?P<flag>[SIEM])"
)
# Look for something like KTLX20250426_121335_V06
re_parts_volume = re.compile(
    r".*(?P<icao>K[A-Z]{3})"
    + r"(?P<time>20\d{2}(0\d|1[012])([012]\d|3[01])_([01]\d|2[0-3])[0-5]\d[0-5]\d)_"
    + r"(?P<kind>V\d{2})"
)

logger = logging.getLogger("radar-data")


class Message:
    """
    A NEXRAD message
    """

    # Page 3-7, Table II Message Header Data
    class Header:
        """
        Message header
        """

        _size_ = 16
        _format_ = ">HBBHHIHH"

        def __init__(self, blob: bytearray, offset: int):
            (
                self.data_size,
                self.channels,
                self.type,
                self.seq_id,
                self.datetime,
                self.datetime_ms,
                self.segments,
                self.seg_num,
            ) = struct.unpack(self._format_, blob[offset : offset + self._size_])

    class Type1:
        # Pages 3-7, Table III Digital Radar Data (Message Type 1)
        class Header:
            """
            Type 1 message header
            """

            _size_ = 100
            _format_ = ">IHhHHHHHHHHHHHHfHHHHH8s2s2s2shhhH32s"

            def __init__(self, blob: bytearray, offset: int):
                (
                    self.timestamp_ms,
                    self.timestamp,
                    self.unambig_range,
                    self.azimuth_angle,
                    self.azimuth_number,
                    self.radial_status,
                    self.elevation_angle,
                    self.elevation_number,
                    self.z_r0,
                    self.v_r0,
                    self.z_dr,
                    self.v_dr,
                    self.z_ngates,
                    self.v_ngates,
                    self.sector_num,
                    self.calib_const,
                    self.z_pointer,
                    self.v_pointer,
                    self.w_pointer,
                    self.v_res,
                    self.vcp,
                    *self.spare,
                ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                if self.v_r0 > 2**15:
                    self.v_r0 -= 2**16

        class Data:
            """
            Type 1 message data block
            """

            nr = 0
            r0 = 0.0
            dr = 0.0
            scale = 1.0
            offset = 0.0
            values = None

            def __init__(self, ngates: int = 0, r0: float = 0.0, dr: float = 0.0):
                self.ngates = ngates
                self.r0 = r0
                self.dr = dr

    class Type5:
        # Page 3-51, Table XI Volume Coverage Pattern Data (Message Type 5 & 7)
        class Header:
            """
            Type 5 message header
            """

            _size_ = 22
            _format_ = ">HHHHHBB10s"

            def __init__(self, blob: bytearray, offset: int):
                (
                    self.msg_size,
                    self.pattern_type,
                    self.pattern_number,
                    self.count,
                    self.clutter_map_group,
                    self.doppler_res,
                    self.pulsewidth,
                    self.spare,
                ) = struct.unpack(self._format_, blob[offset : offset + self._size_])

        class Data:
            """
            Type 5 message elevation data block
            """

            _size_ = 46
            _format_ = ">HBBBBHHhhhhhhHHH2sHHH2sHHH2s"

            def __init__(self, blob: bytearray, offset: int):
                (
                    self.elevation_angle,
                    self.channel_config,
                    self.waveform_type,
                    self.super_res,
                    self.prf_num,
                    self.prf_pulse_count,
                    self.azimuth_rate,
                    self.z_thr,
                    self.v_thr,
                    self.w_thr,
                    self.d_thr,
                    self.p_thr,
                    self.r_thr,
                    self.edge_angle_1,
                    self.prf_num_1,
                    self.prf_pulse_count_1,
                    self.spare_1,
                    self.edge_angle_2,
                    self.prf_num_2,
                    self.prf_pulse_count_2,
                    self.spare_2,
                    self.edge_angle_3,
                    self.prf_num_3,
                    self.prf_pulse_count_3,
                    self.spare_3,
                ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                self.elevation_angle = self.elevation_angle * 180.0 / 32768.0

    class Type31:

        # Pages 3-87, Table XVII Digital Radar Generic Format Blocks (Message Type 31)
        class Header:
            """
            Type 31 message header
            """

            _size_ = 68
            _format_ = ">4sIHHfBBHBBbBfBbHIIIIIIIII"

            def __init__(self, blob: bytearray, offset: int):
                (
                    self.icao,
                    self.timestamp_ms,
                    self.timestamp,
                    self.azimuth_number,
                    self.azimuth_angle,
                    self.compress_flag,
                    self.spare_0,
                    self.radial_length,
                    self.azimuth_resolution,
                    self.radial_spacing,
                    self.elevation_number,
                    self.cut_sector,
                    self.elevation_angle,
                    self.radial_blanking,
                    self.azimuth_mode,
                    self.block_count,
                    *self.block_pointers,
                ) = struct.unpack(self._format_, blob[offset : offset + self._size_])

        class Data:
            # All data blocks begin with a 4-byte header
            class Unknown:
                """
                Unknown data block
                """

                _size_ = 4
                _format_ = ">1s3s"

                def __init__(self, blob: bytearray, offset: int):
                    (
                        self.type,
                        self.name,
                    ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                    self.name = self.name.decode("ascii").strip()

            # Page 3-90, Table XVII-B Data Block for REF, VEL, SW, ZDR, PHI, RHO, and CFP
            class Generic:
                """
                Generic data block
                """

                _size_ = 28
                _format_ = ">1s3sIHhhhhBBff"
                values = None

                def __init__(self, blob: bytearray, offset: int):
                    (
                        self.type,
                        self.name,
                        self.reserved,
                        self.ngates,
                        self.r0,
                        self.dr,
                        self.thr,
                        self.snr_thr,
                        self.flags,
                        self.word_size,
                        self.scale,
                        self.offset,
                    ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                    self.name = self.name.decode("ascii").strip()

            # Page 3-92, Table XVII-E Data Block
            class Volume:
                """
                Volume data block
                """

                _size_ = 44
                _format_ = ">1s3sHBBffhHfffffH2s"

                def __init__(self, blob: bytearray, offset: int):
                    (
                        self.type,
                        self.name,
                        self.lrtup,
                        self.version_major,
                        self.version_minor,
                        self.latitude,
                        self.longitude,
                        self.height,
                        self.feedhorn,
                        self.z_cal,
                        self.power_h,
                        self.power_v,
                        self.d_cal,
                        self.p_cal,
                        self.vcp,
                        *self.spare,
                    ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                    self.name = self.name.decode("ascii")

            # Page 3-93, Table XVII-F Data Block (Elevation Data Constant Type)
            class Elevation:
                """
                Elevation data block
                """

                _size_ = 14
                _format_ = ">1s3sHhHf"

                def __init__(self, blob: bytearray, offset: int):
                    (
                        self.type,
                        self.name,
                        self.lrtup,
                        self.atmos,
                        self.z_cal,
                        self.spare,
                    ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                    self.name = self.name.decode("ascii")

            # Page 3-93, Table XVII-H Data Block (Radial Data Constant Type)
            class Radial:
                """
                Radial data block
                """

                _size_ = 20
                _format_ = ">1s3sHhffh2s"

                def __init__(self, blob: bytearray, offset: int):
                    (
                        self.type,
                        self.name,
                        self.lrtup,
                        self.r_a,
                        self.noise_h,
                        self.noise_v,
                        self.v_a,
                        *self.spare,
                    ) = struct.unpack(self._format_, blob[offset : offset + self._size_])
                    self.name = self.name.decode("ascii")
                    self.v_a *= 0.01  # Convert to m/s

    def __init__(self, blob: bytearray = None, offset: int = 0, skip_type1: bool = False):
        """
        Initializes a NEXRAD message from a byte buffer.

        :param blob: A bytearray containing the message binary data.
        :param offset: Offset in the bytearray where the message starts.
        :param bypass1: If True, skips decoding of MSG1 (message header is still always decoded).
        """
        self.offset = offset
        self.next_offset = offset + METADATA_RECORD_SIZE
        self.info = None
        self.head = None
        self.data = {}
        if blob is not None:
            self.info = self.Header(blob, self.offset)
            if self.info.type == 31:
                self._decode31(blob, offset + self.Header._size_)
                self.next_offset = offset + self.info.data_size * 2 - 4 + self.Header._size_
            elif self.info.type == 5:
                self._decode5(blob, offset + self.Header._size_)
            elif self.info.type == 1 and not skip_type1:
                self._decode1(blob, offset + self.Header._size_)

    def _decode1(self, blob: bytearray, offset: int):
        """
        Decodes as type 1 (Old data format, need more testing)
        """
        self.head = self.Type1.Header(blob, offset)

        if self.head.z_pointer:
            origin = offset + self.head.z_pointer
            values = np.frombuffer(blob[origin : origin + self.head.z_ngates], ">u1")
            block = self.Type1.Data(self.head.z_ngates, self.head.z_r0, self.head.z_dr)
            block.scale = 2.0
            block.offset = 66.0
            block.values = values
            self.data["REF"] = block
        if self.head.v_pointer:
            origin = offset + self.head.v_pointer
            values = np.frombuffer(blob[origin : origin + self.head.v_ngates], ">u1")
            block = self.Type1.Data(self.head.v_ngates, self.head.v_r0, self.head.v_dr)
            block.scale = 1.0 if self.head.v_res == 4 else 2.0
            block.offset = 129.0
            block.values = values
            self.data["VEL"] = block
        if self.head.w_pointer:
            origin = offset + self.head.w_pointer
            values = np.frombuffer(blob[origin : origin + self.head.v_ngates], ">u1")
            block = self.Type1.Data(self.head.v_ngates, self.head.v_r0, self.head.v_dr)
            block.scale = 2.0
            block.offset = 129.0
            block.values = values
            self.data["SW"] = block

    def _decode5(self, blob: bytearray, offset: int):
        """
        Decodes as type 5 (Volume Coverage Pattern Data)
        """
        self.head = self.Type5.Header(blob, offset)
        self.data = []
        offset += self.Type5.Header._size_
        for _ in range(self.head.count):
            self.data.append(self.Type5.Data(blob, offset))
            offset += self.Type5.Data._size_

    def _decode31(self, blob: bytearray, offset: int):
        """
        Decodes as type 31 (Digital Radar Generic Format Blocks)
        """
        self.head = self.Type31.Header(blob, offset)
        for pointer in self.head.block_pointers:
            block = self.Type31.Data.Unknown(blob, offset + pointer)
            if block.name == "VOL":
                block = self.Type31.Data.Volume(blob, offset + pointer)
            elif block.name == "ELV":
                block = self.Type31.Data.Elevation(blob, offset + pointer)
            elif block.name == "RAD":
                block = self.Type31.Data.Radial(blob, offset + pointer)
            elif block.name in ["REF", "VEL", "SW", "ZDR", "PHI", "RHO", "CFP"]:
                block = self.Type31.Data.Generic(blob, offset + pointer)
                origin = offset + pointer + self.Type31.Data.Generic._size_
                if block.word_size == 16:
                    values = np.frombuffer(blob[origin : origin + block.ngates * 2], ">u2")
                else:
                    values = np.frombuffer(blob[origin : origin + block.ngates], ">u1")
                    if block.word_size != 8:
                        print(f"Unexpected word_size = {block.word_size}")
                block.values = values
            self.data[block.name] = block

    @property
    def prf(self):
        """
        Returns the PRF (Pulse Repetition Frequency) of the message. (need more work)
        """
        if self.info.type == 31:
            return self.data["RAD"].v_a / NEXRAD_WAVELENGTH * 4.0
        return 0.0


def _records_from_file(file: str, skip_metadata: bool = True):
    """
    Reads a NEXRAD Level II file and extracts messages

    :param file: Path to the NEXRAD Level II file.
    :return: (VCP, a list of msg31 records) if skip_metadata is True; or
             (metadata, VCP, a list of msg31 records) otherwise.
    """
    # Check if the file is a valid NEXRAD Level II file
    with open(file, "rb") as f:
        content = f.read()
    decompressor = bz2.BZ2Decompressor()
    offset = LDM_CONTROL_WORD_SIZE + (VOLUME_HEADER_SIZE if content[:6] == b"AR2V00" else 0)
    blob = bytearray(decompressor.decompress(content[offset:]))
    while len(decompressor.unused_data):
        unused_data = decompressor.unused_data[LDM_CONTROL_WORD_SIZE:]
        decompressor = bz2.BZ2Decompressor()
        blob += decompressor.decompress(unused_data)
    # Extract messages from the blob
    vcp, meta, msg31, offset = None, [], [], EMPTY_BYTE_COUNT
    while offset < len(blob):
        message = Message(blob, offset)
        if skip_metadata and message.info.type == 15:
            offset = MESSAGE_5_OFFSET
        else:
            offset = message.next_offset
        if message.info.type == 31:
            msg31.append(message)
        elif vcp is None and message.info.type == 5:
            vcp = message
        else:
            meta.append(message)
    if skip_metadata:
        return vcp, msg31
    return meta, vcp, msg31


def _nrays_from_vcp(vcp: Message):
    nrays = []
    for k, scan in enumerate(vcp.data):
        count = 720 if scan.super_res & 0x1 else 360
        logger.debug(f"VCP[{k}] E{scan.elevation_angle:.2f}°  {count} rays")
        nrays.append(count)
    return nrays


def _get_vcp_msg31_timestring_volume(filename: str, **kwargs):
    sweep_index = kwargs.get("sweep_index", 0)
    vcp, msg31 = _records_from_file(filename)
    if vcp is None or len(msg31) == 0:
        raise ValueError(f"Invalid file format: {filename} (vcp = {vcp}), {len(msg31)} msg31)")
    nrays = _nrays_from_vcp(vcp)
    counts = [sum(nrays[:i]) for i in range(len(nrays) + 1)]
    start_end = [slice(x, y) for x, y in zip(counts[:-1], counts[1:])]
    timestring = re_parts_volume.match(os.path.basename(filename))
    if timestring:
        timestring = timestring.groupdict()["time"].replace("_", "-")
    return vcp, msg31[start_end[sweep_index]], timestring


def _get_vcp_msg31_timestring_stripped(filename: str, **kwargs):
    myname = colorize("nexrad._get_vcp_msg31_timestring_stripped", "green")
    sweep_index = kwargs.get("sweep_index", 0)
    folder, basename = os.path.split(filename)
    parts = re_parts_stripped.match(basename)
    if not parts:
        raise ValueError(f"Invalid filename format: {filename}")
    parts = parts.groupdict()
    files = glob.glob(os.path.join(folder, f"{parts['icao']}-{parts['time']}-{parts['scan']}-*"))
    if not files:
        raise ValueError(f"No files found for {filename}")
    files = sorted(files, key=lambda x: int(x.split("-")[-2]))
    # Get VCP info from the first file
    vcp, _ = _records_from_file(files[0])
    nrays = _nrays_from_vcp(vcp)
    nfiles = [x // RADIALS_PER_RECORD for x in nrays]
    counts = [sum(nfiles[:i]) for i in range(len(nfiles) + 1)]
    start_end = [slice(x + 1, y + 1) for x, y in zip(counts[:-1], counts[1:])]
    if sweep_index >= len(start_end):
        raise ValueError(f"Invalid sweep index: {sweep_index} (max {len(start_end) - 1})")
    # Collect message 31 records of the selected sweep_index
    msg31 = []
    for file in files[start_end[sweep_index]]:
        logger.debug(f"{myname} {file}")
        _, m = _records_from_file(file)
        msg31.extend(m)
    timestring = re_parts_stripped.match(os.path.basename(filename))
    if timestring:
        timestring = timestring.groupdict()["time"]
    return vcp, msg31, timestring


def get_vcp_msg31_timestamp(filename: str, **kwargs):
    """
    Extracts VCP and message 31 records from a NEXRAD Level II file.
    :param filename: Path to the NEXRAD Level II file.
    :param kwargs: Optional parameters:
        - sweep_index: Index of the sweep to read (default is 0).
        - verbose: Verbosity level (default is 0).
    :return: A tuple of (VCP, message 31 records, timestamp).
    """
    if filename.endswith("_V06"):
        # V06 single volume format
        vcp, msg31, timestring = _get_vcp_msg31_timestring_volume(filename, **kwargs)
    else:
        # L2-BZIP2 stripped files format
        vcp, msg31, timestring = _get_vcp_msg31_timestring_stripped(filename, **kwargs)
    if not vcp:
        raise ValueError(f"Invalid VCP info in {filename}")
    if len(msg31) == 0:
        raise ValueError(f"No message 31 records found in {filename}")
    if not timestring:
        raise ValueError(f"Invalid filename format: {filename}")
    timestamp = datetime.datetime.strptime(timestring, r"%Y%m%d-%H%M%S")
    timestamp = timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()
    return vcp, msg31, timestamp


def get_nexrad_location(site):
    global NEXRAD
    if len(NEXRAD) == 0:
        if os.path.exists(NEXRAD_DB):
            with open(NEXRAD_DB) as fid:
                NEXRAD = json.load(fid)
        else:
            url = "https://raw.githubusercontent.com/ouradar/radar-data/master/blob/nexrad-locations.json"
            print(f"Retrieving {url} ...")
            response = urllib.request.urlopen(url)
            if response.status == 200:
                nexrad = json.loads(response.read())
                with open(NEXRAD_DB, "w") as fid:
                    json.dump(nexrad, fid)
    key = site.upper()
    if key in NEXRAD:
        return NEXRAD[key]
    return None


def is_nexrad_format(file):
    with open(file, "rb") as f:
        head = f.read(32)
    # KTLX20250426_121335_V06 or KTLX-20250426-121335-999-1-S
    if head[:6] == b"AR2V00":
        return True
    # KTLX-20250426-121335-999-2-I
    #
    # From ICD:
    # The structure of the LDM Compressed Record is a 4-byte, big-endian, signed binary control word
    # followed by a compressed block of Archive II data messages. The control word contains the size, in
    # bytes, of the compressed block not including the control word itself.
    size_in_control_word = abs(struct.unpack(">I", head[:LDM_CONTROL_WORD_SIZE])[0])
    size_match = os.path.getsize(file) - LDM_CONTROL_WORD_SIZE == size_in_control_word
    if size_match and head[LDM_CONTROL_WORD_SIZE : LDM_CONTROL_WORD_SIZE + 3] == b"\x42\x5a\x68":
        return True
    return False
