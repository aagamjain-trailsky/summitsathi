import os
from pathlib import Path

# ── Project root ──────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
STATE_DIR = BASE_DIR / "state" / "data"
IMAGE_DIR = BASE_DIR / "state" / "images"
LOG_DIR   = BASE_DIR / "logs"

# Create directories if they don't exist
for d in [STATE_DIR, IMAGE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── State files ───────────────────────────────────────────────
STATE_FILE   = STATE_DIR / "state.json"
PASSES_FILE  = STATE_DIR / "passes.json"
LATEST_IMAGE = IMAGE_DIR / "latest_apt.png"
LATEST_GEO   = IMAGE_DIR / "latest_apt_geo.json"

# ── Simulator settings ────────────────────────────────────────
SIM_MODE = True  # Set to False when real SDR hardware is connected

SIM_GPS_LAT = 12.9716   # Bangalore — change to your location
SIM_GPS_LON = 77.5946
SIM_GPS_ALT = 920       # metres above sea level

SIM_PASS_INTERVAL_SEC = 60   # how often simulator generates a fake NOAA pass
SIM_IMAGE_UPDATE_SEC  = 30   # how often a new fake decoded image is generated
SIM_GOES_UPDATE_SEC   = 60   # how often GOES fake image refreshes

# ── Satellites ────────────────────────────────────────────────
SATELLITES = {
    # NOAA APT — 137 MHz VHF, polar orbit, passes last ~12 min
    "NOAA-15": {"freq_mhz": 137.620,  "norad_id": 25338, "type": "APT"},
    "NOAA-18": {"freq_mhz": 137.9125, "norad_id": 28654, "type": "APT"},
    "NOAA-19": {"freq_mhz": 137.100,  "norad_id": 33591, "type": "APT"},

    # GOES LRIT — 1694.1 MHz L-band, geostationary, always visible
    "GOES-16": {"freq_mhz": 1694.1,   "norad_id": 41866, "type": "LRIT"},
    "GOES-18": {"freq_mhz": 1694.1,   "norad_id": 51850, "type": "LRIT"},
}

# Which GOES satellite to use as primary (depends on your longitude)
# GOES-16 covers Americas East / Europe / Africa
# GOES-18 covers Americas West / Pacific
GOES_PRIMARY = "GOES-16"

# ── Alert thresholds ──────────────────────────────────────────
STORM_RADIUS_KM      = 30    # alert if storm signature within this radius
STORM_IR_THRESHOLD_K = 220   # brightness temp below this = deep convection

# ── Web UI ────────────────────────────────────────────────────
UI_HOST = "127.0.0.1"
UI_PORT = 5000

# ── Pipeline timing ───────────────────────────────────────────
PASS_PREDICT_HOURS = 24    # hours ahead to predict passes
AOS_LEAD_TIME_SEC  = 120   # start recording this many seconds before AOS

# ── Image settings ────────────────────────────────────────────
APT_IMAGE_WIDTH  = 909     # standard NOAA APT image width in pixels
APT_IMAGE_HEIGHT = 1200    # approximate height per pass
GOES_IMAGE_WIDTH  = 1808   # GOES LRIT full disk width
GOES_IMAGE_HEIGHT = 1808   # GOES LRIT full disk height

# ── Decoder paths (used when SIM_MODE = False) ────────────────
NOAA_APT_DECODER = "noaa-apt"   # must be installed and on PATH
GOES_DECODER     = "goestools"  # must be installed and on PATH
