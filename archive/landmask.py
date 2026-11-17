"""Global land/sea mask at 0.05° rasterised from Natural Earth 1:50m land."""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

RES = 0.05
SRC = config.BASE_DIR / "data" / "reference" / "ne_50m_land.geojson"
CACHE = config.BASE_DIR / "data" / "reference" / "landmask_005.npy"

@lru_cache(maxsize=1)
def land_mask() -> np.ndarray:
    if CACHE.exists():
        return np.load(CACHE)
    w, h = int(360 / RES), int(180 / RES)
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for feat in json.loads(SRC.read_text())["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            for k, ring in enumerate(poly):
                pts = [((lon + 180) / RES, (90 - lat) / RES) for lon, lat in ring]
                draw.polygon(pts, fill=1 if k == 0 else 0)
    mask = np.array(img, dtype=bool)
    np.save(CACHE, mask)
    return mask

def is_land(lat, lon) -> np.ndarray:
    m = land_mask()
    r = np.clip(((90 - np.asarray(lat)) / RES).astype(int), 0, m.shape[0] - 1)
    c = np.clip(((np.asarray(lon) + 180) / RES).astype(int), 0, m.shape[1] - 1)
    return m[r, c]
