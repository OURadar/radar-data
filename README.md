# Radar Data

This is a collection of radar data readers that are in the NetCDF format

These formats are currently supported

- WDSS-II
- CF-Radial 1.3 / CF-1.6
- CF-Radial 1.4 / CF-1.6
- CF-Radial 1.4 / CF-1.7
- CF-Radial 2.0 (draft)
- NEXRAD Level II

## Install Using the Python Package-Management System

```shell
pip install radar-data
```

## Example Usage

```python
import radar

# Get the absolute path of the .nc file, reader automatically gets -V, -W, etc.
file = os.path.expanduser("~/Downloads/data/PX-20240529-150246-E4.0-Z.nc")
sweep = radar.read(file)

# It also works with providing the original .tar.xz or .txz archive
file = os.path.expanduser("~/Downloads/data/PX-20240529-150246-E4.0.txz")
sweep = radar.read(file)

# NEXRAD LDM data feed, simply supply any of the files, the reader reads sweep_index=0 by default
file = os.path.expanduser("~/Downloads/data/KTLX/861/KTLX-20250503-122438-861-1-S")
sweep = radar.read(file)

# The reader finds others in ~/Downloads/data/KTLX/861/ to get to sweep_index=1
file = os.path.expanduser("~/Downloads/data/KTLX/861/KTLX-20250503-122438-861-7-I")
sweep = radar.read(file, sweep_index=1)

# NEXRAD complete volume
file = os.path.expanduser("~/Downloads/data/KTLX/20250503/KTLX20250503_122438_V06")
sweep = radar.read(file, sweep_index=1)
```

## DataShop

```shell
python src/radar/service/datashop.py -v -H 10.197.14.52 -p 50001 -c 4 -t /mnt/data/PX1000/2024/20241219/_original
```
