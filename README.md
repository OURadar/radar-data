# Radar Data

This is a collection of radar data readers that are in the NetCDF format

These formats are currently supported

- WDSS-II
- CF-Radial 1.3 / CF-1.6
- CF-Radial 1.4 / CF-1.6
- CF-Radial 1.4 / CF-1.7
- CF-Radial 2.0 (draft)

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
```
