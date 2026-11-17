import time
import json
import math
import numpy as np
from PIL import Image
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from state.schema import read_state, write_state

# ── Distance calculation ───────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ── Image analysis ─────────────────────────────────────────────
def analyse_image(image_path: str) -> dict:
    try:
        img    = Image.open(image_path).convert("L")
        pixels = np.array(img, dtype=np.float32)

        # Strip sync stripes on left/right edges
        return analyse_pixels(pixels[:, 40:-40])

    except Exception as e:
        print(f"[ALERT] Image analysis failed: {e}")
        return None

def analyse_pixels(centre: np.ndarray) -> dict:
    """Classify a block of image pixels (0-255, bright = cloud)."""
    try:
        centre = centre[np.isfinite(centre)]
        total  = centre.size

        # ── Pixel classification ──────────────────────────────
        clear_pixels      = np.sum(centre < 80)
        low_cloud_pixels  = np.sum((centre >= 80)  & (centre < 130))
        mid_cloud_pixels  = np.sum((centre >= 130) & (centre < 180))
        high_cloud_pixels = np.sum((centre >= 180) & (centre < 220))
        storm_pixels      = np.sum((centre >= 220) & (centre < 245))
        deep_conv_pixels  = np.sum(centre >= 245)
        fog_pixels        = np.sum((centre >= 160) & (centre < 195))
        snow_pixels       = np.sum(centre >= 245)

        # ── Percentages ───────────────────────────────────────
        clear_pct      = round(float(clear_pixels      / total * 100), 1)
        low_cloud_pct  = round(float(low_cloud_pixels  / total * 100), 1)
        mid_cloud_pct  = round(float(mid_cloud_pixels  / total * 100), 1)
        high_cloud_pct = round(float(high_cloud_pixels / total * 100), 1)
        storm_pct      = round(float(storm_pixels      / total * 100), 1)
        deep_conv_pct  = round(float(deep_conv_pixels  / total * 100), 1)
        fog_pct        = round(float(fog_pixels        / total * 100), 1)
        snow_pct       = round(float(snow_pixels       / total * 100), 1)
        cloud_cover    = round(100.0 - clear_pct, 1)

        mean_b = float(np.mean(centre))
        min_b  = float(np.min(centre))

        # ── Rain rate from deep convection ────────────────────
        total_storm = storm_pct + deep_conv_pct
        if total_storm > 4.0:
            rain_rate = "heavy"
        elif total_storm > 1.5:
            rain_rate = "moderate"
        elif total_storm > 0.4:
            rain_rate = "light"
        else:
            rain_rate = "none"

        # ── Humidity proxy from mid-level moisture ────────────
        # Mid and high cloud brightness indicates atmospheric moisture
        humidity_proxy = round(float((mid_cloud_pct + high_cloud_pct * 0.7) / 1.5), 1)
        humidity_proxy = min(humidity_proxy, 100.0)

        # ── Temperature proxy from IR brightness ──────────────
        if mean_b > 210:
            temp_category = "very cold"
        elif mean_b > 170:
            temp_category = "cold"
        elif mean_b > 130:
            temp_category = "cool"
        elif mean_b > 90:
            temp_category = "mild"
        else:
            temp_category = "warm"

        # ── Wind risk proxy from storm structure ──────────────
        # Large deep convection areas indicate strong wind shear
        if deep_conv_pct > 3.0:
            wind_risk = "high"
        elif deep_conv_pct > 1.0 or storm_pct > 3.0:
            wind_risk = "moderate"
        else:
            wind_risk = "low"

        # ── Lightning risk ────────────────────────────────────
        if deep_conv_pct > 2.0:
            lightning_risk = "high"
        elif deep_conv_pct > 0.5:
            lightning_risk = "moderate"
        else:
            lightning_risk = "low"

        # ── Visibility category ───────────────────────────────
        if cloud_cover < 20:
            visibility = "clear"
        elif fog_pct > 2.0:
            visibility = "fog"
        elif cloud_cover < 50:
            visibility = "partly cloudy"
        elif deep_conv_pct > 1.0:
            visibility = "storm"
        elif cloud_cover > 80:
            visibility = "overcast"
        else:
            visibility = "cloudy"

        # ── Precipitation estimate ────────────────────────────
        precipitation = bool(total_storm > 0.4)

        return {
            "cloud_cover_pct":         float(cloud_cover),
            "clear_sky_pct":           float(clear_pct),
            "low_cloud_pct":           float(low_cloud_pct),
            "mid_cloud_pct":           float(mid_cloud_pct),
            "high_cloud_pct":          float(high_cloud_pct),
            "deep_convection_pct":     float(deep_conv_pct),
            "fog_pct":                 float(fog_pct),
            "snow_cover_pct":          float(snow_pct),
            "min_brightness_temp_k":   float(min_b),
            "mean_brightness":         float(mean_b),
            "precipitation_estimated": bool(precipitation),
            "rain_rate":               str(rain_rate),
            "humidity_proxy_pct":      float(humidity_proxy),
            "temp_category":           str(temp_category),
            "wind_risk":               str(wind_risk),
            "lightning_risk":          str(lightning_risk),
            "visibility":              str(visibility)
        }

    except Exception as e:
        print(f"[ALERT] Image analysis failed: {e}")
        return None

# ── Climb risk assessment ──────────────────────────────────────
def assess_climb_risk(conditions: dict, alerts: list) -> dict:
    score = 0
    factors = []

    # Storm proximity alert present
    storm_alerts = [a for a in alerts if a["type"] == "STORM_PROXIMITY"]
    if storm_alerts:
        score += 40
        factors.append("Active storm detected near position")

    # Deep convection
    if conditions["deep_convection_pct"] > 3.0:
        score += 25
        factors.append("Severe deep convection — extreme instability")
    elif conditions["deep_convection_pct"] > 1.0:
        score += 15
        factors.append("Deep convection present — unstable atmosphere")

    # Rain rate
    if conditions["rain_rate"] == "heavy":
        score += 20
        factors.append("Heavy precipitation detected")
    elif conditions["rain_rate"] == "moderate":
        score += 12
        factors.append("Moderate precipitation detected")
    elif conditions["rain_rate"] == "light":
        score += 5
        factors.append("Light precipitation possible")

    # Lightning risk
    if conditions["lightning_risk"] == "high":
        score += 20
        factors.append("High lightning risk — exposed ridgelines dangerous")
    elif conditions["lightning_risk"] == "moderate":
        score += 10
        factors.append("Moderate lightning risk")

    # Wind risk
    if conditions["wind_risk"] == "high":
        score += 15
        factors.append("High wind risk — storm-force winds likely")
    elif conditions["wind_risk"] == "moderate":
        score += 7
        factors.append("Moderate wind risk")

    # Cloud cover
    if conditions["cloud_cover_pct"] > 85:
        score += 5
        factors.append("Heavy cloud cover — poor visibility")

    # Fog
    if conditions["fog_pct"] > 2.0:
        score += 10
        factors.append("Fog detected — navigation hazard")

    # Snow
    if conditions["snow_cover_pct"] > 1.0:
        score += 8
        factors.append("Snow or ice detected — slippery conditions")

    # Humidity (high = more unstable atmosphere)
    if conditions["humidity_proxy_pct"] > 75:
        score += 5
        factors.append("High atmospheric moisture — conditions may deteriorate")

    # Cap score at 100
    score = min(score, 100)

    # ── Risk level ────────────────────────────────────────────
    if score >= 70:
        level    = "EXTREME"
        colour   = "red"
        decision = "DO NOT CLIMB — dangerous conditions present"
    elif score >= 45:
        level    = "HIGH"
        colour   = "orange"
        decision = "High risk — consider turning back or sheltering"
    elif score >= 25:
        level    = "MODERATE"
        colour   = "yellow"
        decision = "Proceed with caution — conditions may worsen"
    elif score >= 10:
        level    = "LOW"
        colour   = "green"
        decision = "Low risk — monitor conditions regularly"
    else:
        level    = "MINIMAL"
        colour   = "green"
        decision = "Conditions favourable for climbing"

    return {
        "score":    int(score),
        "level":    str(level),
        "colour":   str(colour),
        "decision": str(decision),
        "factors":  factors
    }

# ── Storm proximity check ──────────────────────────────────────
def check_storm_proximity(conditions: dict, gps: dict) -> list:
    alerts = []
    if not conditions:
        return alerts

    geo_path = config.LATEST_GEO
    if not geo_path.exists():
        return alerts

    with open(str(geo_path)) as f:
        geo = json.load(f)

    image_lat = geo.get("center_lat", config.SIM_GPS_LAT)
    image_lon = geo.get("center_lon", config.SIM_GPS_LON)
    dist_km   = haversine_km(gps["lat"], gps["lon"], image_lat, image_lon)

    if conditions["precipitation_estimated"] and dist_km < config.STORM_RADIUS_KM * 3:
        severity = "WARNING" if conditions["deep_convection_pct"] > 2.0 else "WATCH"
        alerts.append({
            "id":        f"storm_{int(time.time())}",
            "type":      "STORM_PROXIMITY",
            "severity":  severity,
            "message":   f"Storm system {round(dist_km,1)}km from your position",
            "dist_km":   float(round(dist_km, 1)),
            "issued_at": float(time.time())
        })

    if conditions["rain_rate"] in ["moderate", "heavy"]:
        alerts.append({
            "id":        f"rain_{int(time.time())}",
            "type":      "PRECIPITATION",
            "severity":  "WARNING" if conditions["rain_rate"] == "heavy" else "WATCH",
            "message":   f"{conditions['rain_rate'].capitalize()} rainfall detected",
            "issued_at": float(time.time())
        })

    if conditions["fog_pct"] > 2.0:
        alerts.append({
            "id":        f"fog_{int(time.time())}",
            "type":      "FOG",
            "severity":  "INFO",
            "message":   "Fog detected — reduced visibility",
            "issued_at": float(time.time())
        })

    if conditions["snow_cover_pct"] > 1.0:
        alerts.append({
            "id":        f"snow_{int(time.time())}",
            "type":      "SNOW",
            "severity":  "INFO",
            "message":   "Snow or ice detected in satellite image",
            "issued_at": float(time.time())
        })

    if conditions["lightning_risk"] == "high":
        alerts.append({
            "id":        f"lightning_{int(time.time())}",
            "type":      "LIGHTNING",
            "severity":  "WARNING",
            "message":   "High lightning risk — avoid exposed ridgelines",
            "issued_at": float(time.time())
        })

    if conditions["wind_risk"] == "high":
        alerts.append({
            "id":        f"wind_{int(time.time())}",
            "type":      "WIND",
            "severity":  "WARNING",
            "message":   "High wind risk from storm structure",
            "issued_at": float(time.time())
        })

    return alerts

# ── v3: calibrated Climb Risk Score on real APT passes ─────────
V3_COLOUR = {"MINIMAL": "green", "LOW": "green", "MODERATE": "yellow",
             "HIGH": "orange", "EXTREME": "red"}

def try_v3(image_path: str, state: dict) -> bool:
    """Calibrated 0–100 risk score from archive/risk_v3.py. Needs a real
    APT pass whose geo file carries the TLE and start time."""
    geo_path = config.LATEST_GEO
    if not geo_path.exists():
        return False
    geo_meta = json.loads(geo_path.read_text())
    if not all(k in geo_meta for k in ("tle1", "tle2", "start_utc")):
        return False
    try:
        from pipeline import alert_v3
        model = alert_v3.load_model()
        if model is None:
            return False
        f = alert_v3.location_features(image_path, geo_meta["satellite"], geo_meta["tle1"],
                                       geo_meta["tle2"], geo_meta["start_utc"],
                                       state["gps"]["lat"], state["gps"]["lon"],
                                       previous=state.get("v3_previous"))
        result = alert_v3.assess(f, model)
    except Exception as e:
        print(f"[ALERT] v3 failed ({e}) — falling back")
        return False

    state["climb_risk"] = {
        "score":    result["score"] if result["score"] is not None else 0,
        "level":    result["band"] or result["status"],
        "colour":   V3_COLOUR.get(result["band"], "grey"),
        "decision": result["decision"],
        "factors":  result["factors"],
    }
    state["v3"] = result
    if f:
        state["v3_previous"] = alert_v3.previous_snapshot(f)
    state["alerts"] = [{"id": f"v3_{int(time.time())}", "type": "CLIMB_RISK",
                        "severity": "WARNING" if result["band"] in ("HIGH", "EXTREME") else "INFO",
                        "message": f"Climb risk {result['score']}/100 ({result['band']})"
                                   if result["score"] is not None else result["decision"],
                        "issued_at": float(time.time())}]
    state["updated_at"] = float(time.time())
    write_state(state)
    print(f"[ALERT] v3 climb risk: {result['score']}/100 {result['band'] or result['status']} "
          f"— {result['decision']}")
    for line in result["factors"]:
        print(f"[ALERT]   → {line}")
    return True

# ── v2: real APT passes ────────────────────────────────────────
def try_v2(image_path: str, state: dict) -> bool:
    """Use the v2 model when the image is a real APT pass whose geo file
    carries the TLE and start time. Returns False to fall back to v1."""
    geo_path = config.LATEST_GEO
    if not geo_path.exists():
        return False
    geo_meta = json.loads(geo_path.read_text())
    if not all(k in geo_meta for k in ("tle1", "tle2", "start_utc")):
        return False
    try:
        from pipeline import alert_v2
        models = alert_v2.load_model()
        if not models:
            return False
        f = alert_v2.location_features(image_path, geo_meta["satellite"], geo_meta["tle1"],
                                       geo_meta["tle2"], geo_meta["start_utc"],
                                       state["gps"]["lat"], state["gps"]["lon"])
        if not f:
            print("[ALERT] v2: position outside usable swath — falling back to v1")
            return False
        result = alert_v2.assess(f, models)
    except Exception as e:
        print(f"[ALERT] v2 failed ({e}) — falling back to v1")
        return False

    state["alerts"]     = result["alerts"]
    state["climb_risk"] = result["climb_risk"]
    state["v2"]         = {"probabilities": result["probabilities"],
                           "features": result["features"]}
    state["updated_at"] = float(time.time())
    write_state(state)
    print(f"[ALERT] v2 risk: {result['climb_risk']['level']} — {result['climb_risk']['decision']}")
    for ev, p in result["probabilities"].items():
        print(f"[ALERT]   {ev}: {p:.0%}")
    return True

# ── Main loop ──────────────────────────────────────────────────
def run_alert_engine():
    print("[ALERT] Alert engine starting...")
    last_analysed = None

    while True:
        try:
            state      = read_state()
            image_path = state.get("latest_image", {}).get("filepath")

            if image_path and image_path != last_analysed and try_v3(image_path, state):
                last_analysed = image_path
            elif image_path and image_path != last_analysed and try_v2(image_path, state):
                last_analysed = image_path
            elif image_path and image_path != last_analysed:
                print(f"[ALERT] Analysing: {image_path}")
                conditions = analyse_image(image_path)

                if conditions:
                    alerts     = check_storm_proximity(conditions, state["gps"])
                    climb_risk = assess_climb_risk(conditions, alerts)

                    state["conditions"] = conditions
                    state["alerts"]     = alerts
                    state["climb_risk"] = climb_risk
                    state["updated_at"] = float(time.time())
                    write_state(state)

                    print(f"\n[ALERT] ── Weather Analysis ──────────────────")
                    print(f"[ALERT] Visibility:    {conditions['visibility']}")
                    print(f"[ALERT] Cloud cover:   {conditions['cloud_cover_pct']}%")
                    print(f"[ALERT] Rain rate:     {conditions['rain_rate']}")
                    print(f"[ALERT] Humidity:      {conditions['humidity_proxy_pct']}%")
                    print(f"[ALERT] Wind risk:     {conditions['wind_risk']}")
                    print(f"[ALERT] Lightning:     {conditions['lightning_risk']}")
                    print(f"[ALERT] Snow/ice:      {conditions['snow_cover_pct']}%")
                    print(f"[ALERT] Fog:           {conditions['fog_pct']}%")
                    print(f"[ALERT] Temperature:   {conditions['temp_category']}")
                    print(f"\n[ALERT] ── Climb Risk Assessment ─────────────")
                    print(f"[ALERT] Risk level:    {climb_risk['level']} (score: {climb_risk['score']}/100)")
                    print(f"[ALERT] Decision:      {climb_risk['decision']}")
                    for f in climb_risk['factors']:
                        print(f"[ALERT]   → {f}")
                    if alerts:
                        print(f"\n[ALERT] ── Active Alerts ({len(alerts)}) ───────────────")
                        for a in alerts:
                            print(f"[ALERT]   ⚠️  {a['severity']}: {a['message']}")
                    print(f"[ALERT] ─────────────────────────────────────\n")

                last_analysed = image_path

        except Exception as e:
            print(f"[ALERT] Error: {e}")

        time.sleep(5)

if __name__ == "__main__":
    run_alert_engine()