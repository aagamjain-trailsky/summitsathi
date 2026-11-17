"""
Ground truth for every sample location:

  ERA5 reanalysis (hourly, via Open-Meteo archive API)
  METAR airport observations (via Iowa Environmental Mesonet archive)

Locations are public airports — no personal positions are ever stored.

    python -m archive.truth locations
    python -m archive.truth metar 2019 2025
    python -m archive.truth era5          # after archive.process
"""
import csv
import io
import json
import re
import time
import urllib.request
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import ARCHIVE_DIR

TRUTH_DIR = ARCHIVE_DIR / "truth"
TRUTH_DIR.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "SummitSathi-research/1.0 (student science project)"}

# Mountains / trekking regions first, then a spread of climate zones
LOCATION_IDS = [
    # Himalaya & hills
    "VILH", "VITE", "VISR", "VIJU", "VIGG", "VIBR", "VISM", "VIDN", "VIPT",
    "VEPY", "VEBD", "VEBI", "VEIM", "VELP",
    # Western Ghats & southern hills
    "VOBM", "VOMY", "VOBL", "VOCB", "VOMD", "VOML", "VOCL", "VOKN", "VAPO", "VAKP",
    # Coasts
    "VABB", "VOGO", "VOCI", "VOTV", "VOMM", "VOVZ", "VEBS", "VECC", "VOPB",
    # Plains, desert, north-east
    "VIDP", "VIJP", "VIJO", "VILK", "VEPT", "VAAH", "VABP", "VANP", "VOHS", "VEGT", "VEMN",
]

# Open-Meteo weights requests by variables × days, so keep this list short
ERA5_VARS = ["cloud_cover", "precipitation", "snowfall", "weather_code",
             "wind_gusts_10m", "relative_humidity_2m", "temperature_2m"]


def _get(url: str, retries: int = 5) -> bytes:
    delay = 5
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:
            print(f"[TRUTH] {e} — retry in {delay}s")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Gave up on {url}")


# ── Locations ──────────────────────────────────────────────────
@lru_cache(maxsize=1)
def locations() -> dict:
    cache = TRUTH_DIR / "locations.json"
    if not cache.exists():
        d = json.loads(_get("https://mesonet.agron.iastate.edu/geojson/network/IN__ASOS.geojson"))
        out = {}
        for f in d["features"]:
            p = f["properties"]
            if p["sid"] in LOCATION_IDS:
                lon, lat = f["geometry"]["coordinates"]
                out[p["sid"]] = {"id": p["sid"], "name": p["sname"], "lat": lat, "lon": lon,
                                 "elevation_m": p.get("elevation")}
        cache.write_text(json.dumps(out, indent=1))
    return json.loads(cache.read_text())


# ── ERA5 ───────────────────────────────────────────────────────
def fetch_era5(loc_id: str, year: int, month: int):
    path = TRUTH_DIR / f"era5_{loc_id}_{year}{month:02d}.json"
    if path.exists():
        return
    loc = locations()[loc_id]
    start = datetime(year, month, 1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    url = ("https://archive-api.open-meteo.com/v1/archive"
           f"?latitude={loc['lat']}&longitude={loc['lon']}"
           f"&start_date={start:%Y-%m-%d}&end_date={end:%Y-%m-%d}"
           f"&hourly={','.join(ERA5_VARS)}&timezone=GMT")
    d = json.loads(_get(url))
    path.write_text(json.dumps(d["hourly"]))
    time.sleep(1)

@lru_cache(maxsize=1024)
def _era5(loc_id: str, year: int, month: int) -> dict:
    path = TRUTH_DIR / f"era5_{loc_id}_{year}{month:02d}.json"
    if not path.exists():
        return None
    h = json.loads(path.read_text())
    index = {t: i for i, t in enumerate(h["time"])}
    return {"index": index, "data": h}

def era5_at(loc_id: str, t: datetime, hours_ahead: int = 0) -> dict:
    """ERA5 values at the hour nearest t, plus totals over the next hours."""
    t0 = (t + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    e = _era5(loc_id, t0.year, t0.month)
    if not e:
        return None
    i = e["index"].get(t0.strftime("%Y-%m-%dT%H:%M"))
    if i is None:
        return None
    h = e["data"]
    out = {v: h[v][i] for v in ERA5_VARS}
    if hours_ahead:
        j = min(i + hours_ahead + 1, len(h["time"]))   # truncated at month end
        win = lambda v: [x for x in h[v][i:j] if x is not None]
        out[f"precip_next{hours_ahead}h"] = sum(win("precipitation"))
        out[f"gust_max_next{hours_ahead}h"] = max(win("wind_gusts_10m"), default=None)
    return out


# ── METAR ──────────────────────────────────────────────────────
def fetch_metar(loc_id: str, year: int):
    path = TRUTH_DIR / f"metar_{loc_id}_{year}.csv"
    if path.exists():
        return
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
           f"?station={loc_id}&data=metar&year1={year}&month1=1&day1=1"
           f"&year2={year + 1}&month2=1&day2=1&tz=Etc/UTC&format=onlycomma"
           "&latlon=no&missing=M&trace=T&report_type=3&report_type=4")
    path.write_bytes(_get(url))
    time.sleep(2)

_WX = re.compile(r"(?<!\S)(-|\+|VC)?(MI|BC|PR|DR|BL|SH|TS|FZ)?(DZ|RA|SN|SG|GR|GS|UP|BR|FG|FU|HZ|DU|SA|SQ|FC)+(?!\S)")
_CLOUD = re.compile(r"(?<!\S)(FEW|SCT|BKN|OVC|VV)(\d{3})(CB|TCU)?(?!\S)")
_VIS = re.compile(r"(?<!\S)(\d{4})(?:NDV)?(?!\S)")
OKTAS = {"FEW": 2, "SCT": 4, "BKN": 7, "OVC": 8, "VV": 8}

def parse_metar(text: str) -> dict:
    body = text.split(" RMK")[0].split(" TEMPO")[0].split(" BECMG")[0].split(" NOSIG")[0]
    tokens = body.split()[3:]          # skip ICAO, time, wind
    body = " ".join(tokens)
    wx = [m.group(0) for m in _WX.finditer(body)]
    clouds = _CLOUD.findall(body)
    vis = _VIS.search(body)
    return {
        "thunder": any("TS" in w for w in wx) or any(c[2] == "CB" for c in clouds),
        "rain":    any(p in w for w in wx for p in ("RA", "DZ", "SH", "TS", "GR")),
        "snow":    any("SN" in w for w in wx),
        "fog":     any("FG" in w for w in wx),
        "cb":      any(c[2] == "CB" for c in clouds),
        "oktas":   max([OKTAS[c[0]] for c in clouds], default=0),
        "ceiling_ft": min([int(c[1]) * 100 for c in clouds if c[0] in ("BKN", "OVC", "VV")], default=None),
        "visibility_m": int(vis.group(1)) if vis else (10000 if "CAVOK" in body else None),
    }

@lru_cache(maxsize=256)
def _metar(loc_id: str, year: int) -> list:
    path = TRUTH_DIR / f"metar_{loc_id}_{year}.csv"
    if not path.exists():
        return None
    rows = []
    for r in csv.DictReader(io.StringIO(path.read_text(errors="ignore"))):
        try:
            t = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            continue
        rows.append((t, parse_metar(r["metar"])))
    return rows

def metar_window(loc_id: str, t: datetime, before_h: float = 1, after_h: float = 1) -> dict:
    """Aggregate METAR observations from t-before to t+after."""
    rows = _metar(loc_id, t.year)
    if not rows:
        return None
    lo, hi = t - timedelta(hours=before_h), t + timedelta(hours=after_h)
    win = [m for ts, m in rows if lo <= ts <= hi]
    if not win:
        return None
    vis = [m["visibility_m"] for m in win if m["visibility_m"] is not None]
    return {
        "n_reports": len(win),
        "thunder":   any(m["thunder"] for m in win),
        "rain":      any(m["rain"] for m in win),
        "snow":      any(m["snow"] for m in win),
        "fog":       any(m["fog"] for m in win),
        "cb":        any(m["cb"] for m in win),
        "oktas_max": max(m["oktas"] for m in win),
        "vis_min_m": min(vis) if vis else None,
    }


def fetch_metar_all(year0: int, year1: int):
    locs = locations()
    print(f"[TRUTH] METAR for {len(locs)} locations, {year0}–{year1}")
    for loc_id in locs:
        for y in range(year0, year1 + 1):
            try:
                fetch_metar(loc_id, y)
            except Exception as e:
                print(f"[TRUTH] {loc_id} {y}: {e}")
        print(f"[TRUTH] {loc_id} done")

def fetch_era5_needed(workers: int = 4):
    """ERA5 only for location-months that have satellite samples."""
    from archive.db import connect
    from concurrent.futures import ThreadPoolExecutor
    conn = connect()
    need = [(r["location"], *map(int, r["ym"].split("-"))) for r in conn.execute(
        "SELECT DISTINCT location, substr(time_utc, 1, 7) ym FROM samples ORDER BY ym")]
    print(f"[TRUTH] ERA5 for {len(need)} location-months")

    def one(job):
        try:
            fetch_era5(*job)
        except Exception as e:
            print(f"[TRUTH] {job}: {e}")

    with ThreadPoolExecutor(workers) as ex:
        for k, _ in enumerate(ex.map(one, need), 1):
            if k % 50 == 0:
                print(f"[TRUTH] {k}/{len(need)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "locations"
    if cmd == "locations":
        for l in locations().values():
            print(l["id"], l["name"], round(l["lat"], 2), round(l["lon"], 2), l["elevation_m"])
    elif cmd == "metar":
        fetch_metar_all(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "era5":
        fetch_era5_needed()
