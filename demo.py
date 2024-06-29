import numpy as np
import src.radar as radar

dummy_sweep = {
    "kind": "U",
    "txrx": "M",
    "symbol": "Z",
    "time": 1369071296.0,
    "latitude": 35.25527,
    "longitude": -97.422413,
    "sweepElevation": 4.0,
    "sweepAzimuth": 42.0,
    "gatewidth": 150.0,
    "waveform": "s01",
    "prf": 1000.0,
    "elevations": np.array([15, 14.0, 14.2, 16.0], dtype=np.float32),
    "azimuths": np.array([15.0, 30.0, 45.0, 60.0], dtype=np.float32),
    "products": {
        "Z": np.array([[0, 22, -1, -5], [-11, -6, -9, -12], [9, 14, 9, 5], [24, 29, 34, 40]], dtype=np.float32),
        "V": np.array([[1, -3, 4, 6], [-12, -10, -9, -10], [11, 9, 3, 2], [-3, -10, -9, -5]], dtype=np.float32),
    },
}

radar.pprint(dummy_sweep)
