"""
Check georeferencing against real coastlines.

For clean daytime passes, land is brighter than sea in the visible channel
where the sky is clear. We shift the assumed line timing and try both scan
directions; the alignment that best matches the Natural Earth land mask
tells us whether the geometry is right (offset ≈ 0, not mirrored).

    python -m archive.validate_geo 20
"""
import json
import numpy as np
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import connect, ARCHIVE_DIR
from archive import apt, geo
from archive.landmask import is_land
from scipy.ndimage import uniform_filter
from archive.process import TLE_NAME
from pyorbital.astronomy import sun_zenith_angle

OFFSETS = list(range(-10, 31, 2))
MIRRORS = (False,)   # mirror=True was ruled out on real passes (see README)


def _highpass(x, valid, size=15):
    """Remove broad brightness trends so only coastline-scale detail is compared."""
    x = np.where(valid, x, 0.0)
    w = uniform_filter(valid.astype(float), size)
    return x - uniform_filter(x, size) / np.maximum(w, 1e-6)

def score_pass(row) -> dict:
    r = apt.process(row["image_path"])
    vis_rows = np.isin(r["channel_a"], ["1", "2"])
    if vis_rows.sum() < 300 or r["frames_calibrated"] == 0:
        return None

    vis = r["image_a"][:, ::2]
    bt = r["bt_b"][:, ::2]
    valid = np.isfinite(vis) & vis_rows[:, None] & (bt > 285)   # clear, daylit
    v = _highpass(vis, valid)

    results = []
    for mirror in MIRRORS:
        for off in OFFSETS:
            la, lo, _ = geo.geolocate(TLE_NAME[row["satellite"]], row["tle1"], row["tle2"],
                                      row["start_utc"], r["n_lines"], step=2,
                                      time_offset_s=off, mirror=mirror)
            land = is_land(la, lo).astype(float)
            near_coast = uniform_filter(land, 15)
            m = valid & (near_coast > 0.05) & (near_coast < 0.95)
            if m.sum() < 1000:
                return None
            c = np.corrcoef(v[m], _highpass(land, valid)[m])[0, 1]
            results.append((float(c), off, mirror))
    results.sort(reverse=True)
    best = results[0]
    base = [x for x in results if x[1] == 0 and not x[2]][0]
    return {"obs_id": row["obs_id"], "station_id": row["station_id"],
            "best_corr": best[0], "best_offset": best[1],
            "best_mirror": best[2], "corr_at_zero": base[0]}


def run(n: int = 20):
    conn = connect()
    # Daytime passes over India: roughly 03:00–10:00 UTC
    rows = [dict(r) for r in conn.execute("""
        SELECT o.* FROM observations o
        WHERE download_status='ok' AND max_elev_deg >= 40
          AND CAST(substr(start_utc, 12, 2) AS INT) BETWEEN 3 AND 10
          AND COALESCE((SELECT verdict FROM station_quality q
                        WHERE q.station_id = o.station_id), '') != 'bad'
        ORDER BY max_elev_deg DESC LIMIT ?""", (n * 3,))]
    out = []
    for row in rows:
        try:
            s = score_pass(row)
        except Exception as e:
            print(f"[GEO] {row['obs_id']}: {e}")
            continue
        if s:
            out.append(s)
            print(f"[GEO] {s['obs_id']}: best r={s['best_corr']:.2f} at offset {s['best_offset']}s "
                  f"(r at 0s = {s['corr_at_zero']:.2f}) station {s['station_id']}", flush=True)
        if len(out) >= n:
            break

    if not out:
        print("[GEO] No suitable clear daytime passes found yet")
        return
    # Only clear coastline matches are trusted for the offset estimate
    strong = [s for s in out if s["best_corr"] > 0.15]
    per_station = {}
    for st in sorted({s["station_id"] for s in out}):
        offs = [s["best_offset"] for s in strong if s["station_id"] == st]
        per_station[st] = {"passes": sum(s["station_id"] == st for s in out),
                           "strong": len(offs), "offsets": offs,
                           "median_offset_s": float(np.median(offs)) if offs else None}
    all_offs = [s["best_offset"] for s in strong]
    summary = {"passes": len(out), "strong_matches": len(strong),
               "median_offset_s": float(np.median(all_offs)) if all_offs else None,
               "per_station": per_station}
    (ARCHIVE_DIR / "results").mkdir(exist_ok=True)
    (ARCHIVE_DIR / "results" / "geo_validation.json").write_text(
        json.dumps({"summary": summary, "passes": out}, indent=1))
    print(f"\n[GEO] Summary: {summary}")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
