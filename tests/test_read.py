import os
import sys
import urllib.request

TEST_FILE_FOLDER = "data"
TEST_FILES = [
    "BS1-20230616-020024-E6.4.txz",
    "cfrad.20080604_002217_000_SPOL_v36_SUR.nc",
    "KTLX20250217_204640_V06",
    "KTLX-20250503-165233-900-3-I",
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
        url = f"https://radarhub/static/radar-data-test.txz"
        urllib.request.urlretrieve(url, "_radar-data-test.txz")
        print(f"Extracting test data ...")
        os.system(f"tar -x -v -C {TEST_FILE_FOLDER} -f _radar-data-test.txz")
        os.remove("_radar-data-test.txz")


def test_read():
    """
    Test the read function
    """
    file_path = os.path.join(TEST_FILE_FOLDER, TEST_FILES[0])
    data = radar.read(file_path)
    assert data is not None, "Failed to read the file"
    radar.print(data)


# Example usage
if __name__ == "__main__":

    download_data_if_not_exists()

    test_read()
