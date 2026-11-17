import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

ARCHIVE_DIR = config.BASE_DIR / "data" / "archive"
RAW_DIR     = ARCHIVE_DIR / "raw"
DB_PATH     = ARCHIVE_DIR / "archive.db"

for d in [ARCHIVE_DIR, RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Only what the analysis needs. Observer usernames and station names are
# deliberately not stored; station position is rounded to ~10 km.
SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    obs_id        INTEGER PRIMARY KEY,
    norad_id      INTEGER NOT NULL,
    satellite     TEXT    NOT NULL,
    start_utc     TEXT    NOT NULL,
    end_utc       TEXT    NOT NULL,
    max_elev_deg  REAL,
    rise_az_deg   REAL,
    set_az_deg    REAL,
    tle1          TEXT,
    tle2          TEXT,
    station_id    INTEGER,
    station_lat   REAL,
    station_lon   REAL,
    image_url     TEXT,
    image_path    TEXT,
    download_status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS crawl_progress (
    station_id INTEGER,
    norad_id   INTEGER,
    done       INTEGER DEFAULT 0,
    next_url   TEXT,
    PRIMARY KEY (station_id, norad_id)
);
CREATE TABLE IF NOT EXISTS station_quality (
    station_id  INTEGER PRIMARY KEY,
    sampled     INTEGER,
    with_signal INTEGER,
    best_score  REAL,
    verdict     TEXT
);
CREATE TABLE IF NOT EXISTS images (
    obs_id          INTEGER PRIMARY KEY,
    n_lines         INTEGER,
    good_lines      INTEGER,
    sync_quality    REAL,
    channel_a       INTEGER,
    channel_b       INTEGER,
    calibrated      INTEGER,
    processed_path  TEXT,
    error           TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    obs_id      INTEGER,
    location    TEXT,
    time_utc    TEXT,
    view_angle  REAL,
    features    TEXT,
    PRIMARY KEY (obs_id, location)
);
"""

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=120)
    conn.row_factory = sqlite3.Row
    # WAL lets the crawler, downloader and processor write at the same time
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
