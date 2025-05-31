import os
import urllib.request

TEST_FILE_FOLDER = "data"
TEST_FILES = [
    "BS1-20230616-020024-E6.4.txz",
    "cfrad.20080604_002217_000_SPOL_v36_SUR.nc",
    "cfrad.20150625_050022_PX1000_v35_s1.nc",
    "cfrad.20211011_201557.188_to_20211011_201617.720_DOW8_PPI.nc",
    "cfrad.20211011_201711.345_to_20211011_201732.860_DOW8_PPI.nc",
    "KTLX-20250503-165233-900-13-I",
    "KTLX20250217_204640_V06",
    "PX-20240529-150246-E4.0-Z.nc",
    "PX-20240529-150246-E4.0.tar.xz",
    "PX-20241221-125419-E6.0.nc",
    "PX-20241221-125419-E6.0.txz",
    "RK-20240729-175543-E2.0.nc.txz",
]

import src.radar as radar


def download_data_if_not_exists():
    """
    Downloads test data if not exists
    """
    any_missing = False
    for file in TEST_FILES:
        file = os.path.join(TEST_FILE_FOLDER, file)
        if not os.path.exists(file):
            any_missing = True
            break
    if any_missing:
        print(f"Downloading test data ...")
        url = f"https://radarhub.arrc.ou.edu/static/radar-data-test.txz"
        urllib.request.urlretrieve(url, "_radar-data-test.txz")
        print(f"Extracting test data ...")
        os.makedirs(TEST_FILE_FOLDER, exist_ok=True)
        os.system(f"tar -x -v -C {TEST_FILE_FOLDER} -f _radar-data-test.txz")
        os.remove("_radar-data-test.txz")


def test_read():
    """
    Test the read function
    """
    for file in TEST_FILES:
        file = os.path.join(TEST_FILE_FOLDER, file)
        print(f"Testing file {file}")
        if not os.path.exists(file):
            print(f"File {file} does not exist")
            data = radar.read(file)
            assert data is not None, "Failed to read the file"


# Example usage
if __name__ == "__main__":

    download_data_if_not_exists()

    test_read()
