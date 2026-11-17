"""
Run every downloaded real APT pass through calibration, georeferencing and
feature extraction for each sample location inside the swath.

    python -m archive.process            # all unprocessed passes
    python -m archive.process 50         # first 50 only
    python -m archive.process --all      # clear and reprocess everything
"""
import json
import numpy as np
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import connect, ARCHIVE_DIR
from archive import apt, geo
from archive.truth import locations
from pipeline.alert_engine import analyse_pixels
from pyorbital.astronomy import sun_zenith_angle
from scipy.ndimage import uniform_filter

CROP_DIR = ARCHIVE_DIR / "crops"
CROP_DIR.mkdir(parents=True, exist_ok=True)

HALF = 8                 # 17×17 pixel box ≈ 65 km at nadir
MAX_SCAN_DEG = 50        # beyond this, pixels are too stretched to trust
STORM_SEARCH_KM = 500.0  # storm distance is capped at this
TLE_NAME = {"NOAA-15": "NOAA 15", "NOAA-18": "NOAA 18", "NOAA-19": "NOAA 19"}

# Georeferencing checked against coastlines (validate_geo.py): not mirrored;
# line timing offset measured per station where a clear pass exists, else 0 s.
GEO_TIME_OFFSET_S = 0.0
GEO_MIRROR = False

def station_offsets() -> tuple:
    """Per-station line-timing offsets, plus the median over all clear
    coastline matches as the default for stations without their own."""
    path = ARCHIVE_DIR / "results" / "geo_validation.json"
    if not path.exists():
        return {}, GEO_TIME_OFFSET_S
    summary = json.loads(path.read_text())["summary"]
    per = summary.get("per_station", {})
    default = summary.get("median_offset_s")
    return ({int(k): v["median_offset_s"] for k, v in per.items() if v["median_offset_s"] is not None},
            GEO_TIME_OFFSET_S if default is None else default)


def _locate_all(plat, plon, locs):
    """Nearest (line, pixel) for every location; None if outside the swath."""
    p1, l1 = np.radians(plat), np.radians(plon)
    out = {}
    for loc in locs:
        p0, l0 = np.radians(loc["lat"]), np.radians(loc["lon"])
        d = geo.R_EARTH * np.arccos(np.clip(np.sin(p0) * np.sin(p1) +
                                            np.cos(p0) * np.cos(p1) * np.cos(l1 - l0), -1, 1))
        i, j = np.unravel_index(np.argmin(d), d.shape)
        if d[i, j] < 20 and 0 < i < plat.shape[0] - 1:
            out[loc["id"]] = (int(i), int(j) * 4)
    return out

def bt_features(bt: np.ndarray) -> dict:
    v = bt[np.isfinite(bt)]
    if v.size < 50:
        return {}
    return {
        "bt_min":   float(v.min()),
        "bt_p10":   float(np.percentile(v, 10)),
        "bt_p50":   float(np.median(v)),
        "bt_mean":  float(v.mean()),
        "bt_std":   float(v.std()),
        "frac_lt_273": float((v < 273).mean()),   # below freezing
        "frac_lt_253": float((v < 253).mean()),   # mid/high cloud
        "frac_lt_233": float((v < 233).mean()),   # deep convective tops
        "frac_lt_220": float((v < 220).mean()),   # overshooting tops
    }

def fog_features(bt4: np.ndarray, bt3b: np.ndarray) -> dict:
    """Night fog / low cloud: water droplets emit less at 3.7 µm than at
    11 µm, so BT4 − BT3B is positive over fog and low stratus."""
    m = np.isfinite(bt4) & np.isfinite(bt3b)
    if m.sum() < 50:
        return {}
    d = (bt4 - bt3b)[m]
    return {"bt3b_p50": float(np.median(bt3b[m])),
            "btd_p50": float(np.median(d)),
            "btd_p90": float(np.percentile(d, 90)),
            "frac_btd_gt2": float((d > 2).mean())}

def storm_distance_features(lat0, lon0, plat, plon, bt_grid) -> dict:
    """Distance from the location to the nearest deep-convective cloud top
    (< 233 K) anywhere in the pass, and how much of it is nearby."""
    cold = np.isfinite(bt_grid) & (bt_grid < 233)
    if not cold.any():
        return {"storm_dist_km": STORM_SEARCH_KM, "cold_px_50km": 0.0, "cold_px_150km": 0.0}
    p1, l1 = np.radians(plat[cold]), np.radians(plon[cold])
    p0, l0 = np.radians(lat0), np.radians(lon0)
    d = geo.R_EARTH * np.arccos(np.clip(np.sin(p0) * np.sin(p1) +
                                        np.cos(p0) * np.cos(p1) * np.cos(l1 - l0), -1, 1))
    return {"storm_dist_km": float(min(d.min(), STORM_SEARCH_KM)),
            "cold_px_50km": float((d < 50).sum()),
            "cold_px_150km": float((d < 150).sum())}

def overshooting_tops(bt_grid: np.ndarray) -> np.ndarray:
    """Pixels much colder (≥ 6 K) than their surroundings and below 225 K —
    the signature of updrafts punching through the anvil of a strong storm."""
    valid = np.isfinite(bt_grid)
    x = np.where(valid, bt_grid, 0.0)
    w = uniform_filter(valid.astype(float), 7)
    local_mean = uniform_filter(x, 7) / np.maximum(w, 1e-6)
    return valid & (bt_grid < 225) & (local_mean - bt_grid >= 6)

def structure_features(lat0, lon0, plat, plon, bt_grid, ot_mask, crop_bt) -> dict:
    """Storm structure around the location (v3)."""
    p1, l1 = np.radians(plat), np.radians(plon)
    p0, l0 = np.radians(lat0), np.radians(lon0)
    d = geo.R_EARTH * np.arccos(np.clip(np.sin(p0) * np.sin(p1) +
                                        np.cos(p0) * np.cos(p1) * np.cos(l1 - l0), -1, 1))
    f = {}
    for r_km in (50, 100):
        ring = (d < r_km) & np.isfinite(bt_grid)
        if ring.sum() < 10:
            continue
        v = bt_grid[ring]
        f[f"bt_min_{r_km}km"] = float(v.min())
        f[f"bt_std_{r_km}km"] = float(v.std())
        f[f"frac_lt_233_{r_km}km"] = float((v < 233).mean())
        f[f"frac_lt_253_{r_km}km"] = float((v < 253).mean())
        f[f"ot_count_{r_km}km"] = float((ot_mask & (d < r_km)).sum())
    g = crop_bt[np.isfinite(crop_bt)]
    if g.size >= 50:
        gy, gx = np.gradient(np.where(np.isfinite(crop_bt), crop_bt, np.nanmedian(crop_bt)))
        f["bt_grad_mean"] = float(np.hypot(gx, gy).mean())
        f["bt_grad_max"] = float(np.hypot(gx, gy).max())
    return f

def visible_features(vis: np.ndarray, bt: np.ndarray, sza: float) -> dict:
    """Daytime: storm clouds are cold AND bright; thin cirrus is cold but
    dim. Reflectance proxy = counts / 255 / cos(solar zenith)."""
    m = np.isfinite(vis) & np.isfinite(bt)
    if m.sum() < 50 or sza >= 80:
        return {}
    refl = vis[m] / 255.0 / max(np.cos(np.radians(sza)), 0.17)
    cold = bt[m] < 253
    return {"vis_refl_mean": float(refl.mean()),
            "vis_refl_p90": float(np.percentile(refl, 90)),
            "frac_bright_cold": float((cold & (refl > 0.5)).mean()),
            "frac_dim_cold": float((cold & (refl < 0.3)).mean())}

def counts_features(x: np.ndarray, prefix: str) -> dict:
    v = x[np.isfinite(x)]
    if v.size < 50:
        return {}
    return {f"{prefix}_mean": float(v.mean()),
            f"{prefix}_p90": float(np.percentile(v, 90)),
            f"{prefix}_std": float(v.std())}

def process_one(row: dict) -> dict:
    try:
        r = apt.process(row["image_path"])
    except Exception as e:
        return {"obs_id": row["obs_id"], "error": str(e), "samples": []}

    result = {"obs_id": row["obs_id"], "error": None, "samples": [],
              "image": {k: r[k] for k in ("n_lines", "good_lines", "sync_quality",
                                          "frames_calibrated")}}
    chans_b = {c for c in r["channel_b"] if c}
    result["image"]["channel_a"] = ",".join(sorted({c for c in r["channel_a"] if c}))
    result["image"]["channel_b"] = ",".join(sorted(chans_b))
    if r["frames_calibrated"] == 0:
        result["error"] = "no calibrated frames"
        return result

    offset = row.get("time_offset_s", GEO_TIME_OFFSET_S)
    plat, plon, times = geo.geolocate(TLE_NAME[row["satellite"]], row["tle1"], row["tle2"],
                                      row["start_utc"], r["n_lines"], step=4,
                                      time_offset_s=offset, mirror=GEO_MIRROR)
    hits = _locate_all(plat, plon, list(locations().values()))
    scan = np.degrees(geo.scan_angles()) * (-1 if GEO_MIRROR else 1)
    bt_grid = r["bt_b"][:, ::4]             # matches the step-4 geolocation grid
    ot_mask = overshooting_tops(bt_grid)

    for loc_id, (i, j) in hits.items():
        if abs(scan[j]) > MAX_SCAN_DEG:
            continue
        rows = slice(max(i - HALF, 0), i + HALF + 1)
        cols = slice(max(j - HALF, 0), j + HALF + 1)
        if not r["line_ok"][rows].mean() > 0.7:
            continue

        t = times[i].astype(datetime)
        loc = locations()[loc_id]
        sza = float(sun_zenith_angle(t, loc["lon"], loc["lat"]))
        crop_a, crop_b, crop_bt = r["image_a"][rows, cols], r["image_b"][rows, cols], r["bt_b"][rows, cols]

        # The channel-ID wedge often reads 3B as 3A; 3A (reflected sunlight)
        # cannot be observed in darkness, so a dark scene means 3B.
        ch_a = r["channel_a"][i]
        if ch_a == "3A" and sza > 95:
            ch_a = "3B"

        local_hour = (t.hour + t.minute / 60 + loc["lon"] / 15) % 24
        f = {"channel_a": ch_a, "channel_b": r["channel_b"][i],
             "sun_zenith": sza, "scan_angle": float(scan[j]),
             "local_hour": float(local_hour), "elevation_m": loc.get("elevation_m")}
        f.update(bt_features(crop_bt))
        f.update(storm_distance_features(loc["lat"], loc["lon"], plat, plon, bt_grid))
        f.update(structure_features(loc["lat"], loc["lon"], plat, plon, bt_grid, ot_mask, crop_bt))
        if ch_a == "3B":
            f.update(fog_features(crop_bt, r["bt_a"][rows, cols]))
        f.update(counts_features(crop_b, "b"))
        if r["channel_a"][i] in ("1", "2") and sza < 80:
            f.update(counts_features(crop_a, "vis"))
            f.update(visible_features(crop_a, crop_bt, sza))

        # v1: the original alert engine, unchanged, on the channel-B crop
        v1 = analyse_pixels(crop_b.astype(np.float32))
        if v1:
            f["v1"] = v1

        np.savez_compressed(CROP_DIR / f"{row['obs_id']}_{loc_id}.npz",
                            a=crop_a.astype(np.float16), b=crop_b.astype(np.float16),
                            bt=crop_bt.astype(np.float16))
        result["samples"].append({"location": loc_id, "time_utc": t.strftime("%Y-%m-%dT%H:%M:%S"),
                                  "view_angle": float(scan[j]), "features": f})
    return result


def run(limit: int = None, workers: int = 6):
    conn = connect()
    q = """SELECT o.* FROM observations o LEFT JOIN images i ON o.obs_id = i.obs_id
           LEFT JOIN station_quality q ON q.station_id = o.station_id
           WHERE o.download_status = 'ok' AND i.obs_id IS NULL
             AND COALESCE(q.verdict, '') != 'bad'
           ORDER BY o.start_utc"""
    rows = [dict(r) for r in conn.execute(q + (f" LIMIT {int(limit)}" if limit else ""))]
    offsets, default = station_offsets()
    for r in rows:
        r["time_offset_s"] = offsets.get(r["station_id"], default)
    print(f"[PROCESS] {len(rows)} passes to process "
          f"(timing offsets: {offsets or 'none'}, default {default} s)")

    n_samples = n_ok = 0
    with ProcessPoolExecutor(workers) as ex:
        for k, res in enumerate(ex.map(process_one, rows, chunksize=4), 1):
            img = res.get("image", {})
            conn.execute("""INSERT OR REPLACE INTO images
                (obs_id, n_lines, good_lines, sync_quality, channel_a, channel_b,
                 calibrated, error) VALUES (?,?,?,?,?,?,?,?)""",
                (res["obs_id"], img.get("n_lines"), img.get("good_lines"), img.get("sync_quality"),
                 img.get("channel_a"), img.get("channel_b"), img.get("frames_calibrated"), res["error"]))
            for s in res["samples"]:
                conn.execute("""INSERT OR REPLACE INTO samples
                    (obs_id, location, time_utc, view_angle, features) VALUES (?,?,?,?,?)""",
                    (res["obs_id"], s["location"], s["time_utc"], s["view_angle"],
                     json.dumps(s["features"])))
            n_samples += len(res["samples"])
            n_ok += res["error"] is None
            if k % 25 == 0:
                conn.commit()
                print(f"[PROCESS] {k}/{len(rows)} passes, {n_ok} usable, {n_samples} location samples")
    conn.commit()
    print(f"[PROCESS] Done: {n_ok}/{len(rows)} usable passes, {n_samples} location samples")


def reset():
    """Forget processed results so every pass is processed again."""
    conn = connect()
    conn.execute("DELETE FROM samples")
    conn.execute("DELETE FROM images")
    conn.commit()
    for f in CROP_DIR.glob("*.npz"):
        f.unlink()
    print("[PROCESS] Cleared previous results")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--all":
        reset()
        args = args[1:]
    run(int(args[0]) if args else None)
