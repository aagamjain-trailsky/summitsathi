"""
Crawl SatNOGS for real, archived NOAA APT passes recorded by ground
stations around India, then download the decoded images.

    python -m archive.collect stations     # list regional stations
    python -m archive.collect crawl        # fetch observation metadata
    python -m archive.collect download     # fetch the APT images
    python -m archive.collect status
"""
import json
import time
import urllib.request
import urllib.error
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import connect, RAW_DIR, ARCHIVE_DIR

API = "https://network.satnogs.org/api"
NOAA = {25338: "NOAA-15", 28654: "NOAA-18", 33591: "NOAA-19"}

# Stations in this box can receive passes whose swath covers India
REGION = {"lat": (0.0, 40.0), "lon": (55.0, 100.0)}

# NOAA APT ended in 2025; nothing usable after this
END_UTC = "2025-08-31T00:00:00Z"

# Station screening: sample this many of the highest passes; a station is
# kept if any has real APT structure (pure noise scores ~2, real images 5–50)
SCREEN_N = 6
SIGNAL_SCORE = 5.0

HEADERS = {"User-Agent": "TrailSky-research/1.0 (student science project)"}

# Optional SatNOGS API key for higher rate limits. Kept in a private file
# (chmod 600) and never printed or logged.
TOKEN_FILE = Path(__file__).parent.parent / ".satnogs_token"

def _auth_headers(url: str) -> dict:
    if url.startswith(API) and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return {**HEADERS, "Authorization": f"Token {token}"}
    return HEADERS

# ── HTTP with polite rate limiting ─────────────────────────────
def get(url: str, retries: int = 60):
    delay = 2
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=_auth_headers(url))
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read(), r.headers
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = int(e.headers.get("Retry-After") or delay)
                print(f"[COLLECT] HTTP {e.code}, waiting {wait}s")
                time.sleep(wait)
                delay = min(delay * 2, 120)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[COLLECT] {e}, retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise RuntimeError(f"Gave up on {url}")

def next_link(headers) -> str:
    link = headers.get("Link") or ""
    for part in link.split(","):
        if 'rel="next"' in part:
            return part[part.index("<") + 1: part.index(">")]
    return None

# ── Stations ───────────────────────────────────────────────────
def regional_stations() -> list:
    cache = ARCHIVE_DIR / "stations.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        stations = json.loads(cache.read_text())
    else:
        body, _ = get(f"{API}/stations/?format=json")
        stations = json.loads(body)
        # Keep only what we use
        stations = [{"id": s["id"], "lat": s["lat"], "lng": s["lng"],
                     "observations": s.get("observations") or 0}
                    for s in stations if s.get("lat") is not None]
        cache.write_text(json.dumps(stations))

    (la0, la1), (lo0, lo1) = REGION["lat"], REGION["lon"]
    # Busiest stations first, so most passes arrive early under rate limits
    return sorted([s for s in stations
                   if la0 <= s["lat"] <= la1 and lo0 <= s["lng"] <= lo1
                   and s["observations"] > 0],
                  key=lambda s: -s["observations"])

# ── Crawl observation metadata ─────────────────────────────────
def store(conn, o: dict):
    pngs = [d["payload_demod"] for d in o.get("demoddata", [])
            if d["payload_demod"].lower().endswith(".png")]
    if not pngs or o.get("transmitter_mode") != "APT":
        return False
    conn.execute("""
        INSERT OR IGNORE INTO observations
        (obs_id, norad_id, satellite, start_utc, end_utc, max_elev_deg,
         rise_az_deg, set_az_deg, tle1, tle2, station_id,
         station_lat, station_lon, image_url)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (o["id"], o["norad_cat_id"], NOAA[o["norad_cat_id"]],
         o["start"], o["end"], o.get("max_altitude"),
         o.get("rise_azimuth"), o.get("set_azimuth"),
         o.get("tle1"), o.get("tle2"), o["ground_station"],
         round(o["station_lat"], 1) if o.get("station_lat") is not None else None,
         round(o["station_lng"], 1) if o.get("station_lng") is not None else None,
         pngs[0]))
    return True

def _fetch_page(conn, station_id, norad) -> int:
    """Fetch the next page of observations for one station/satellite."""
    row = conn.execute(
        "SELECT done, next_url FROM crawl_progress WHERE station_id=? AND norad_id=?",
        (station_id, norad)).fetchone()
    if row and row["done"]:
        return -1
    url = (row["next_url"] if row and row["next_url"] else
           f"{API}/observations/?ground_station={station_id}&norad_cat_id={norad}"
           f"&status=good&end={END_UTC}&format=json")
    body, headers = get(url)
    obs = [o for o in json.loads(body) if o["norad_cat_id"] == norad]
    added = sum(store(conn, o) for o in obs)
    nxt = next_link(headers)
    conn.execute("""INSERT OR REPLACE INTO crawl_progress
                    (station_id, norad_id, done, next_url) VALUES (?,?,?,?)""",
                 (station_id, norad, 0 if nxt else 1, nxt))
    conn.commit()
    time.sleep(4.0)   # SatNOGS throttles anonymous clients
    return added

def image_score(path) -> float:
    """Spread of the column means. Real APT has strong vertical structure
    (sync, telemetry, space strips); pure noise is flat (~2)."""
    img = np.array(Image.open(path).convert("L"), dtype=np.float32)
    live = img[img.max(axis=1) > 0]
    return float(live.mean(axis=0).std()) if len(live) else 0.0

def screen_station(conn, station_id) -> str:
    """Download a few of the highest passes; is this station producing images?"""
    q = conn.execute("SELECT verdict FROM station_quality WHERE station_id=?", (station_id,)).fetchone()
    if q:
        return q["verdict"]
    rows = [dict(r) for r in conn.execute("""SELECT obs_id, image_url FROM observations
            WHERE station_id=? ORDER BY max_elev_deg DESC LIMIT ?""", (station_id, SCREEN_N))]
    if not rows:
        return "empty"
    scores = []
    for r in rows:
        obs_id, path, st = _download(r)
        conn.execute("UPDATE observations SET image_path=?, download_status=? WHERE obs_id=?",
                     (path, st, obs_id))
        if path:
            scores.append(image_score(path))
    with_signal = sum(sc >= SIGNAL_SCORE for sc in scores)
    verdict = "good" if with_signal else "bad"
    conn.execute("""INSERT OR REPLACE INTO station_quality
                    (station_id, sampled, with_signal, best_score, verdict) VALUES (?,?,?,?,?)""",
                 (station_id, len(scores), with_signal, max(scores, default=0), verdict))
    conn.commit()
    print(f"[COLLECT] station {station_id}: {with_signal}/{len(scores)} sampled images have signal "
          f"(best score {max(scores, default=0):.1f}) → {verdict}")
    return verdict

def crawl():
    conn = connect()
    stations = regional_stations()
    auth = "with API key" if TOKEN_FILE.exists() else "anonymous"
    print(f"[COLLECT] {len(stations)} regional stations ({auth})")

    for s in stations:
        # 1. First page per satellite, then check the images are real
        added = sum(max(_fetch_page(conn, s["id"], n), 0) for n in NOAA)
        if added:
            print(f"[COLLECT] station {s['id']}: +{added} (first pages)")
        verdict = screen_station(conn, s["id"])
        if verdict != "good":
            conn.execute("UPDATE crawl_progress SET done=1 WHERE station_id=?", (s["id"],))
            conn.commit()
            continue

        # 2. Only stations producing real images get their full history crawled
        for norad in NOAA:
            added = 0
            while (n := _fetch_page(conn, s["id"], norad)) >= 0:
                added += n
            if added:
                print(f"[COLLECT] station {s['id']} {NOAA[norad]}: +{added}")

    status()

# ── Download images ────────────────────────────────────────────
def _download(row) -> tuple:
    path = RAW_DIR / f"{row['obs_id']}.png"
    if path.exists() and path.stat().st_size > 0:
        return row["obs_id"], str(path), "ok"
    try:
        body, _ = get(row["image_url"])
        path.write_bytes(body)
        return row["obs_id"], str(path), "ok"
    except Exception as e:
        return row["obs_id"], None, f"error: {e}"

def download(limit: int = None, workers: int = 4):
    conn = connect()
    q = """SELECT o.obs_id, o.image_url FROM observations o
           LEFT JOIN station_quality q ON q.station_id = o.station_id
           WHERE o.download_status != 'ok' AND COALESCE(q.verdict, '') != 'bad'
           ORDER BY o.start_utc"""
    rows = conn.execute(q + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    print(f"[COLLECT] Downloading {len(rows)} images...")

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for obs_id, path, st in ex.map(_download, rows):
            conn.execute("UPDATE observations SET image_path=?, download_status=? WHERE obs_id=?",
                         (path, st, obs_id))
            done += 1
            conn.commit()
            if done % 50 == 0:
                print(f"[COLLECT] {done}/{len(rows)}")
    conn.commit()
    status()

def status():
    conn = connect()
    print("\n[COLLECT] ── Archive status ──────────────────")
    for r in conn.execute("""SELECT satellite, COUNT(*) n,
                             SUM(download_status='ok') dl,
                             MIN(start_utc) first, MAX(start_utc) last
                             FROM observations GROUP BY satellite"""):
        print(f"[COLLECT] {r['satellite']}: {r['n']} passes, {r['dl'] or 0} downloaded, "
              f"{r['first'][:10]} → {r['last'][:10]}")
    for r in conn.execute("SELECT verdict, COUNT(*) n FROM station_quality GROUP BY verdict"):
        print(f"[COLLECT] stations screened {r['verdict']}: {r['n']}")
    pending = conn.execute("SELECT COUNT(*) FROM crawl_progress WHERE done=0").fetchone()[0]
    print(f"[COLLECT] Crawl jobs unfinished: {pending}\n")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "stations":
        for s in regional_stations():
            print(s["id"], round(s["lat"], 1), round(s["lng"], 1), s["observations"])
    elif cmd == "crawl":
        crawl()
    elif cmd == "download":
        download(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        status()
