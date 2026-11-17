import sys
import time
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from state.schema import read_state, write_state

CDN_BASE = "https://cdn.star.nesdis.noaa.gov/GOES19/ABI/FD/13"

def build_timestamp(dt: datetime) -> str:
    """NOAA format: YYYYDDDHHMM where DDD is day of year, rounded to 10 min."""
    minute = (dt.minute // 10) * 10
    dt = dt.replace(minute=minute, second=0, microsecond=0)
    year = dt.strftime("%Y")
    doy  = dt.strftime("%j")
    hhmm = dt.strftime("%H%M")
    return f"{year}{doy}{hhmm}"

def get_recent_urls() -> list:
    """Build URLs for the last ~90 minutes of 10-minute intervals."""
    now = datetime.now(timezone.utc)
    urls = []
    for i in range(9):
        dt = now - timedelta(minutes=i * 10)
        ts = build_timestamp(dt)
        url = f"{CDN_BASE}/{ts}_GOES19-ABI-FD-13-1808x1808.jpg"
        urls.append((ts, url))
    return urls

def fetch_goes_image():
    headers = {
        "User-Agent": "Mozilla/5.0 SummitSathi/1.0",
        "Referer":    "https://www.star.nesdis.noaa.gov/"
    }

    for ts, url in get_recent_urls():
        print(f"[REAL] Trying timestamp {ts}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()

            if len(data) < 50000:
                print(f"[REAL] Too small ({len(data)} bytes), skipping")
                continue

            filepath = config.IMAGE_DIR / f"real_GOES19_{int(time.time())}.jpg"
            with open(str(filepath), "wb") as f:
                f.write(data)
            with open(str(config.LATEST_IMAGE), "wb") as f:
                f.write(data)

            print(f"[REAL] Got real GOES-19 image - {len(data):,} bytes - timestamp {ts}")
            return filepath, ts

        except urllib.error.HTTPError as e:
            print(f"[REAL] {ts} -> HTTP {e.code}")
            continue
        except Exception as e:
            print(f"[REAL] {ts} -> {e}")
            continue

    print("[REAL] All recent timestamps failed")
    return None, None

def update_state(filepath: Path, timestamp: str):
    geo = {
        "satellite":     "GOES-19",
        "type":          "LRIT",
        "captured_at":   float(time.time()),
        "filepath":      str(filepath),
        "center_lat":    0.0,
        "center_lon":    -75.0,
        "pixel_size_km": 2.0,
        "projection":    "geostationary",
        "source_timestamp": timestamp
    }
    with open(str(config.LATEST_GEO), "w") as f:
        json.dump(geo, f, indent=2)

    state = read_state()
    state["updated_at"] = float(time.time())
    state["latest_image"] = {
        "satellite":    "GOES-19",
        "type":         "LRIT",
        "captured_at":  float(time.time()),
        "filepath":     str(filepath),
        "geo_filepath": str(config.LATEST_GEO)
    }
    state["pipeline"]["sdr_active"]          = False
    state["pipeline"]["currently_recording"] = False
    state["pipeline"]["recording_satellite"] = "GOES-19"
    state["pipeline"]["sim_mode"]            = False
    write_state(state)
    print("[REAL] State updated with real GOES-19 image")

def run_real_fetcher():
    print("[REAL] Real GOES-19 fetcher starting...")
    print("[REAL] Source: NOAA STAR CDN (real-time GOES-19 Band 13 IR)")
    last_fetch = 0

    while True:
        now = time.time()
        if now - last_fetch > 600:
            filepath, ts = fetch_goes_image()
            if filepath:
                update_state(filepath, ts)
                last_fetch = now
            else:
                print("[REAL] Retrying in 60 seconds...")
                time.sleep(60)
                continue
        time.sleep(10)

if __name__ == "__main__":
    run_real_fetcher()