import time
import json
import random
import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from state.schema import read_state, write_state, read_passes, write_passes

def generate_apt_image(satellite_name: str) -> Path:
    width  = config.APT_IMAGE_WIDTH
    height = config.APT_IMAGE_HEIGHT

    noise = np.random.randint(20, 80, (height, width), dtype=np.uint8)
    img   = Image.fromarray(noise, mode="L")
    draw  = ImageDraw.Draw(img)

    for _ in range(random.randint(3, 7)):
        x1 = random.randint(0, width - 200)
        y1 = random.randint(0, height - 200)
        x2 = x1 + random.randint(100, 400)
        y2 = y1 + random.randint(100, 300)
        draw.ellipse([x1, y1, x2, y2], fill=random.randint(80, 140))

    for _ in range(random.randint(4, 10)):
        x1 = random.randint(0, width - 200)
        y1 = random.randint(0, height - 100)
        x2 = x1 + random.randint(150, 400)
        y2 = y1 + random.randint(40, 120)
        draw.ellipse([x1, y1, x2, y2], fill=random.randint(160, 255))

    if random.random() < 0.4:
        sx = random.randint(100, width - 100)
        sy = random.randint(100, height - 100)
        draw.ellipse([sx-40, sy-40, sx+40, sy+40], fill=255)

    for y in range(0, height, 8):
        val = 255 if (y // 8) % 2 == 0 else 0
        draw.line([(0, y), (39, y)], fill=val)
        draw.line([(width-40, y), (width-1, y)], fill=val)

    filepath = config.IMAGE_DIR / f"apt_{satellite_name}_{int(time.time())}.png"
    img.save(str(filepath))
    img.save(str(config.LATEST_IMAGE))
    return filepath

def generate_geo_file(filepath: Path, satellite_name: str) -> Path:
    geo = {
        "satellite":    satellite_name,
        "type":         "APT",
        "captured_at":  float(time.time()),
        "filepath":     str(filepath),
        "center_lat":   float(config.SIM_GPS_LAT + random.uniform(-5, 5)),
        "center_lon":   float(config.SIM_GPS_LON + random.uniform(-5, 5)),
        "pixel_size_km": 2.0,
        "projection":   "mercator"
    }
    geo_path = config.LATEST_GEO
    with open(str(geo_path), "w") as f:
        json.dump(geo, f, indent=2)
    return geo_path

def generate_pass(satellite_name: str) -> dict:
    now = float(time.time())
    aos = now + float(random.randint(30, 120))
    los = aos + float(random.randint(600, 900))
    return {
        "satellite":      satellite_name,
        "type":           "APT",
        "aos":            aos,
        "los":            los,
        "max_elevation":  int(random.randint(15, 89)),
        "frequency_mhz":  float(config.SATELLITES[satellite_name]["freq_mhz"]),
        "predicted_snr":  float(round(random.uniform(6.0, 22.0), 1))
    }

def run_simulator():
    print("[SIM] Satellite simulator starting...")
    last_image_time = 0.0
    last_pass_time  = 0.0

    while True:
        now = float(time.time())

        if now - last_pass_time > config.SIM_PASS_INTERVAL_SEC:
            passes = [generate_pass(s) for s in ["NOAA-15", "NOAA-18", "NOAA-19"]]
            passes.sort(key=lambda x: x["aos"])
            write_passes({"updated_at": now, "passes": passes})
            last_pass_time = now
            print(f"[SIM] Generated {len(passes)} fake passes")

        if now - last_image_time > config.SIM_IMAGE_UPDATE_SEC:
            sat = random.choice(["NOAA-15", "NOAA-18", "NOAA-19"])
            print(f"[SIM] Generating fake APT image from {sat}...")
            filepath = generate_apt_image(sat)
            geo_path = generate_geo_file(filepath, sat)

            state = read_state()
            state["updated_at"] = now
            state["latest_image"] = {
                "satellite":    sat,
                "type":         "APT",
                "captured_at":  now,
                "filepath":     str(filepath),
                "geo_filepath": str(geo_path)
            }
            state["pipeline"]["sdr_active"]          = False
            state["pipeline"]["currently_recording"] = False
            state["pipeline"]["recording_satellite"] = sat
            state["pipeline"]["sim_mode"]            = True
            write_state(state)
            last_image_time = now
            print(f"[SIM] Image saved to {filepath}")

        time.sleep(5)

if __name__ == "__main__":
    run_simulator()