#!/bin/bash

python -m build

version=$(grep "__version__" src/radar/__init__.py | awk -F'"' '{print $2}')
archive=$(ls -t dist/radar_data-${version}.tar.gz)

echo "version = ${version}   archive = ${archive}"

python -m twine upload --verbose --repository radar-data ${archive}
