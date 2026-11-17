"""
v2 alert logic — thresholds and model learned from real NOAA APT passes
scored against airport weather reports (see archive/README.md).

Works on a real decoded APT image (2080 px wide) plus the pass TLE and
start time; v1 in alert_engine.py remains the fallback for anything else.
"""
import json
import math
import time
import numpy as np
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive import apt, geo
from archive.process import (bt_features, storm_distance_features, fog_features,
                             TLE_NAME, HALF, GEO_MIRROR, MAX_SCAN_DEG)
from archive.evaluate import MODEL_PATH
from pyorbital.astronomy import sun_zenith_angle


def load_model() -> dict:
    return json.loads(MODEL_PATH.read_text()) if MODEL_PATH.exists() else {}

def location_features(image_path, satellite, tle1, tle2, start_utc, lat, lon,
                      time_offset_s=0.0) -> dict:
    """Same features as the archive study, for one position."""
    r = apt.process(image_path)
    if r["frames_calibrated"] == 0:
        return None
    plat, plon, times = geo.geolocate(TLE_NAME.get(satellite, satellite), tle1, tle2, start_utc,
                                      r["n_lines"], step=4, time_offset_s=time_offset_s,
                                      mirror=GEO_MIRROR)
    p1, l1 = np.radians(plat), np.radians(plon)
    d = geo.R_EARTH * np.arccos(np.clip(np.sin(math.radians(lat)) * np.sin(p1) +
                                        math.cos(math.radians(lat)) * np.cos(p1) *
                                        np.cos(l1 - math.radians(lon)), -1, 1))
    i, j4 = np.unravel_index(np.argmin(d), d.shape)
    j = j4 * 4
    scan = float(np.degrees(geo.scan_angles()[j]))
    if d[i, j4] > 20 or abs(scan) > MAX_SCAN_DEG:
        return None                      # position outside the usable swath

    rows = slice(max(i - HALF, 0), i + HALF + 1)
    cols = slice(max(j - HALF, 0), j + HALF + 1)
    t = times[i].astype(datetime)
    sza = float(sun_zenith_angle(t, lon, lat))
    ch_a = r["channel_a"][i]
    if ch_a == "3A" and sza > 95:
        ch_a = "3B"
    local_hour = (t.hour + t.minute / 60 + lon / 15) % 24

    f = {"sun_zenith": sza, "abs_scan": abs(scan), "is_day": float(sza < 85),
         "hour_sin": math.sin(2 * math.pi * local_hour / 24),
         "hour_cos": math.cos(2 * math.pi * local_hour / 24),
         "month_sin": math.sin(2 * math.pi * t.month / 12),
         "month_cos": math.cos(2 * math.pi * t.month / 12)}
    f.update(bt_features(r["bt_b"][rows, cols]))
    f.update(storm_distance_features(lat, lon, plat, plon, r["bt_b"][:, ::4]))
    if ch_a == "3B":
        f.update(fog_features(r["bt_b"][rows, cols], r["bt_a"][rows, cols]))
    f["has_3b"] = float("btd_p50" in f)
    f["time_utc"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f

def probability(model: dict, f: dict) -> float:
    m = model["logistic"]
    x = np.array([f.get(k, np.nan) for k in m["features"]], dtype=float)
    z = np.nan_to_num((x - np.array(m["mu"])) / np.array(m["sd"]))
    return float(1 / (1 + math.exp(-(z @ np.array(m["w"]) + m["b"]))))

def assess(f: dict, models: dict = None) -> dict:
    """Alerts and climb risk from v2 models."""
    models = models or load_model()
    probs, alerts, now = {}, [], float(time.time())
    for ev, m in models.items():
        probs[ev] = probability(m, f)
        if probs[ev] >= m["logistic"]["prob_threshold"]:
            alerts.append({"id": f"{ev}_{int(now)}", "type": ev.upper(), "severity": "WARNING",
                           "message": f"{ev.replace('_', ' ')}: {probs[ev]:.0%} probability",
                           "probability": probs[ev], "issued_at": now})

    dist = f.get("storm_dist_km")
    if dist is not None and dist < 50:
        alerts.append({"id": f"storm_{int(now)}", "type": "STORM_PROXIMITY",
                       "severity": "WARNING" if dist < 20 else "WATCH",
                       "message": f"Deep convective cloud {dist:.0f} km from your position",
                       "dist_km": dist, "issued_at": now})

    p_thunder = max(probs.get("thunder_now", 0), probs.get("rain_next3h", 0))
    if p_thunder >= 0.5 or (dist is not None and dist < 20):
        level, colour, decision = "EXTREME", "red", "DO NOT CLIMB — thunderstorm at or near your position"
    elif p_thunder >= 0.3 or (dist is not None and dist < 50):
        level, colour, decision = "HIGH", "orange", "High risk — consider turning back or sheltering"
    elif p_thunder >= 0.15 or probs.get("fog_now", 0) >= 0.3:
        level, colour, decision = "MODERATE", "yellow", "Proceed with caution — conditions may worsen"
    else:
        level, colour, decision = "LOW", "green", "No storm signature in the latest pass"

    return {"version": "v2", "probabilities": probs, "alerts": alerts,
            "climb_risk": {"level": level, "colour": colour, "decision": decision,
                           "score": int(round(p_thunder * 100)),
                           "factors": [a["message"] for a in alerts]},
            "features": {k: v for k, v in f.items() if isinstance(v, (int, float))}}
