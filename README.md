# Radar Data

This is a collection of radar data readers that are in the NetCDF format

These formats are currently supported

- WDSS-II
- CF-Radial 1.3
- CF-Radial 2.0 (draft)

## Install Using the Python Package-Management System

```shell
pip install radar-data
```

## Example Usage

```python
import radar

file = os.path.expanduser("~/Downloads/data/PX-20240529-150246-E4.0-Z.nc")
sweep = radar.read(file)
```
