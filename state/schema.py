import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bool):
            return bool(obj)
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)

def default_state():
    return {
        "updated_at": time.time(),
        "gps": {
            "lat": float(config.SIM_GPS_LAT),
            "lon": float(config.SIM_GPS_LON),
            "alt": float(config.SIM_GPS_ALT),
            "fix": False
        },
        "latest_image": {
            "satellite": None,
            "type": None,
            "captured_at": None,
            "filepath": None,
            "geo_filepath": None
        },
        "conditions": {
            "cloud_cover_pct": 0.0,
            "min_brightness_temp_k": 300.0,
            "precipitation_estimated": False,
            "visibility": "unknown"
        },
        "alerts": [],
        "pipeline": {
            "sdr_active": False,
            "currently_recording": False,
            "recording_satellite": None,
            "sim_mode": bool(config.SIM_MODE)
        },
        "goes": {
            "GOES-16": {
                "last_image_at": None,
                "filepath": None,
                "status": "waiting"
            },
            "GOES-18": {
                "last_image_at": None,
                "filepath": None,
                "status": "waiting"
            }
        }
    }

def default_passes():
    return {
        "updated_at": time.time(),
        "passes": []
    }

def write_state(state: dict):
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, cls=JSONEncoder)

def read_state() -> dict:
    if not config.STATE_FILE.exists():
        s = default_state()
        write_state(s)
        return s
    try:
        with open(config.STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        s = default_state()
        write_state(s)
        return s

def write_passes(passes: dict):
    with open(config.PASSES_FILE, "w") as f:
        json.dump(passes, f, indent=2, cls=JSONEncoder)

def read_passes() -> dict:
    if not config.PASSES_FILE.exists():
        p = default_passes()
        write_passes(p)
        return p
    try:
        with open(config.PASSES_FILE, "r") as f:
            return json.load(f)
    except Exception:
        p = default_passes()
        write_passes(p)
        return p