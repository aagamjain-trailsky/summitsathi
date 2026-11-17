"""
v3 Climb Risk Score for the live system.

Score 0–100 = calibrated chance of a hazard (thunderstorm now, rain within
3 h, or fog) at the hiker's position, from the model trained and checked in
archive/risk_v3.py. Only calibrated numbers are shown; everything else is
reported as plain-language factors.

Status is never "safe" by default:
  NO DATA  no usable satellite view of the position
  STALE    the latest pass is older than the model's validity window
"""
import math
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive import apt, geo
from archive.process import (bt_features, storm_distance_features, fog_features, structure_features,
                             visible_features, overshooting_tops, TLE_NAME, HALF, GEO_MIRROR,
                             MAX_SCAN_DEG)
from archive.evaluate import RESULTS_DIR, climatology
from archive.evaluate_v3 import ALL_TIME
from archive.risk_v3 import SAFETY_RULES, band
from archive.truth import locations
from pyorbital.astronomy import sun_zenith_angle

MODEL_PATH = RESULTS_DIR / "model_risk_v3.pkl"
COOLING_KEYS = (("bt_min", "d_bt_min_per_h"), ("bt_min_100km", "d_bt_min_100km_per_h"),
                ("frac_lt_233_100km", "d_frac_lt_233_100km_per_h"))


def load_model():
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)

def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - lon1)
    return geo.R_EARTH * np.arccos(np.clip(np.sin(p1) * np.sin(p2) +
                                           np.cos(p1) * np.cos(p2) * np.cos(dl), -1, 1))

def nearest_airport(lat, lon) -> tuple:
    locs = list(locations().values())
    d = [_haversine_km(lat, lon, l["lat"], l["lon"]) for l in locs]
    k = int(np.argmin(d))
    return locs[k], float(d[k])


def location_features(image_path, satellite, tle1, tle2, start_utc, lat, lon,
                      time_offset_s=8.0, previous=None):
    """All v3 inputs for one position on one real APT pass, or None."""
    r = apt.process(image_path)
    if r["frames_calibrated"] == 0:
        return None
    plat, plon, times = geo.geolocate(TLE_NAME.get(satellite, satellite), tle1, tle2, start_utc,
                                      r["n_lines"], step=4, time_offset_s=time_offset_s,
                                      mirror=GEO_MIRROR)
    d = _haversine_km(lat, lon, plat, plon)
    i, j4 = np.unravel_index(np.argmin(d), d.shape)
    j = j4 * 4
    scan = float(np.degrees(geo.scan_angles()[j]))
    rows = slice(max(i - HALF, 0), i + HALF + 1)
    cols = slice(max(j - HALF, 0), j + HALF + 1)
    if d[i, j4] > 20 or abs(scan) > MAX_SCAN_DEG or r["line_ok"][rows].mean() <= 0.7:
        return None

    t = times[i].astype(datetime)
    sza = float(sun_zenith_angle(t, lon, lat))
    ch_a = r["channel_a"][i]
    if ch_a == "3A" and sza > 95:
        ch_a = "3B"
    local_hour = (t.hour + t.minute / 60 + lon / 15) % 24
    crop_a, crop_b, crop_bt = r["image_a"][rows, cols], r["image_b"][rows, cols], r["bt_b"][rows, cols]
    bt_grid = r["bt_b"][:, ::4]

    f = {"sun_zenith": sza, "abs_scan": abs(scan), "is_day": float(sza < 85),
         "local_hour": local_hour,
         "hour_sin": math.sin(2 * math.pi * local_hour / 24),
         "hour_cos": math.cos(2 * math.pi * local_hour / 24),
         "month_sin": math.sin(2 * math.pi * t.month / 12),
         "month_cos": math.cos(2 * math.pi * t.month / 12)}
    f.update(bt_features(crop_bt))
    f.update(storm_distance_features(lat, lon, plat, plon, bt_grid))
    f.update(structure_features(lat, lon, plat, plon, bt_grid, overshooting_tops(bt_grid), crop_bt))
    if ch_a in ("1", "2"):
        f.update(visible_features(crop_a, crop_bt, sza))
    if ch_a == "3B":
        f.update(fog_features(crop_bt, r["bt_a"][rows, cols]))
    f["has_3b"] = float("btd_p50" in f)

    # Cooling rate against the previous pass over this position
    f["has_prev"] = 0.0
    if previous:
        gap = (t - datetime.fromisoformat(previous["time"])).total_seconds() / 3600
        if 0.3 <= gap <= 4.0:
            f["has_prev"], f["prev_gap_h"] = 1.0, gap
            for key, out in COOLING_KEYS:
                if key in f and key in previous:
                    f[out] = (f[key] - previous[key]) / gap

    # Local climate history from the nearest airport
    airport, airport_km = nearest_airport(lat, lon)
    row = [{"location": airport["id"], "time": t, "features": f}]
    for ev_flag, feat in (("rain_now", "clim_rain"), ("thunder_now", "clim_thunder"),
                          ("fog_now", "clim_fog"), ("cloudy_now", "clim_cloudy")):
        f[feat] = float(climatology(row, ev_flag, ALL_TIME)[0])

    f["_time"] = t.replace(tzinfo=timezone.utc).isoformat()
    f["_airport"] = airport["name"].title()
    f["_airport_km"] = airport_km
    return f


def factors(f) -> list:
    """Plain-language reasons behind the score."""
    out = []
    dist = f.get("storm_dist_km")
    if dist is not None and dist < 500:
        out.append(f"Storm cloud (colder than −40 °C) {dist:.0f} km away")
    if f.get("ot_count_50km", 0) > 0:
        out.append(f"{f['ot_count_50km']:.0f} overshooting storm tops within 50 km")
    if f.get("bt_min_100km") is not None:
        out.append(f"Coldest cloud top within 100 km: {f['bt_min_100km'] - 273.15:.0f} °C")
    if f.get("d_bt_min_100km_per_h") is not None and f["d_bt_min_100km_per_h"] < -3:
        out.append(f"Cloud tops cooling {-f['d_bt_min_100km_per_h']:.0f} °C per hour — storm growing")
    if f.get("frac_bright_cold", 0) > 0.2:
        out.append("Thick, bright storm cloud overhead")
    if f.get("btd_p50") is not None and f["btd_p50"] > 2:
        out.append("Night fog or low cloud signal")
    if f.get("clim_thunder", 0) > 0.1:
        out.append(f"Thunderstorms are common here at this time of year and day "
                   f"({100 * f['clim_thunder']:.0f}% of reports at {f['_airport']})")
    return out


def assess(f, model=None, now=None) -> dict:
    model = model or load_model()
    now = now or datetime.now(timezone.utc)
    if model is None:
        return {"version": "v3", "status": "NO MODEL", "score": None, "band": None,
                "decision": "Risk model not installed — run archive/risk_v3.py", "factors": []}
    if f is None:
        return {"version": "v3", "status": "NO DATA", "score": None, "band": None,
                "decision": "No usable satellite view of your position — use other weather sources",
                "factors": []}

    x = np.array([[f.get(k, np.nan) for k in model["features"]]], float)
    score = 100 * float(model["calibration"].predict(model["model"].predict_proba(x)[:, 1])[0])
    applied = []
    for name, cond in SAFETY_RULES:
        floor = model["floors"].get(name, {}).get("floor_score")
        if floor is not None and cond(f) and score < floor:
            score = float(floor)
            applied.append(name)
    score = int(round(score))
    b = band(score)

    age_h = (now - datetime.fromisoformat(f["_time"])).total_seconds() / 3600
    status = "STALE" if age_h > model["stale_after_hours"] else "CURRENT"
    decision = model["decision"][b]
    if status == "STALE":
        decision = (f"Latest pass is {age_h:.1f} h old — conditions may have changed. "
                    f"At pass time: {decision.lower()}")

    return {"version": "v3", "status": status, "score": score, "band": b,
            "decision": decision, "pass_time_utc": f["_time"], "pass_age_h": round(age_h, 1),
            "safety_rules_applied": applied, "factors": factors(f),
            "nearest_airport": f["_airport"], "nearest_airport_km": round(f["_airport_km"], 1)}


def previous_snapshot(f) -> dict:
    """What to keep for the next pass's cooling-rate calculation."""
    if not f:
        return None
    snap = {k: f[k] for k, _ in COOLING_KEYS if k in f}
    snap["time"] = datetime.fromisoformat(f["_time"]).replace(tzinfo=None).isoformat()
    return snap
