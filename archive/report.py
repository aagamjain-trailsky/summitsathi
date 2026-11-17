"""
Figures for the v3 results: performance curves, the safety trade-off,
what the model relies on, where the data comes from, and real case studies.

    python -m archive.report          # writes data/archive/results/figures/*.png
"""
import json
import pickle
import sqlite3
import numpy as np
from datetime import datetime
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import DB_PATH
from archive.evaluate import RESULTS_DIR, build_dataset
from archive.evaluate_v3 import add_cooling_features, set_climatology, matrix, TEST_GROUPS
from archive.truth import locations, metar_window
from archive.landmask import SRC as LAND_GEOJSON
from archive import apt, geo
from archive.process import TLE_NAME, station_offsets
from archive.risk_v3 import band as _band

def band_name(score):
    return None if score is None else _band(score)

FIG_DIR = RESULTS_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Formal, restrained palette (Minfy brand neutrals; orange only as a highlight)
NAVY, GREY, ORANGE, INK, MUTED, GRID = "#0A2540", "#8C8C8C", "#E85D26", "#333333", "#6B6B6B", "#E6E6E6"
plt.rcParams.update({
    "font.family": "serif", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "figure.dpi": 150,
    "savefig.bbox": "tight", "savefig.facecolor": "white", "lines.linewidth": 2,
})

EVENT_NAME = {"thunder_now": "Thunderstorm", "rain_now": "Rain (now)",
              "rain_next3h": "Rain in the next 3 hours", "fog_now": "Fog"}
FEATURE_NAME = {
    "clim_thunder": "Airport thunderstorm history", "clim_rain": "Airport rain history",
    "clim_fog": "Airport fog history", "clim_cloudy": "Airport cloud history",
    "bt_min": "Coldest cloud top (box)", "bt_p10": "Cold cloud tops, 10th pct (box)",
    "bt_p50": "Median cloud-top temperature", "bt_std": "Cloud-top temperature spread",
    "bt_min_50km": "Coldest cloud top within 50 km", "bt_min_100km": "Coldest cloud top within 100 km",
    "bt_std_50km": "Temperature spread within 50 km", "bt_std_100km": "Temperature spread within 100 km",
    "frac_lt_233_100km": "Deep storm cloud within 100 km", "frac_lt_253_100km": "High cloud within 100 km",
    "frac_lt_233_50km": "Deep storm cloud within 50 km", "frac_lt_253_50km": "High cloud within 50 km",
    "ot_count_50km": "Overshooting tops within 50 km", "ot_count_100km": "Overshooting tops within 100 km",
    "cold_px_50km": "Storm cloud pixels within 50 km", "cold_px_150km": "Storm cloud pixels within 150 km",
    "storm_dist_km": "Distance to nearest storm cloud", "bt_grad_mean": "Cloud-top temperature edges",
    "bt_grad_max": "Sharpest cloud-top edge", "vis_refl_mean": "Cloud brightness (visible)",
    "vis_refl_p90": "Brightest cloud (visible)", "frac_bright_cold": "Thick storm cloud (cold + bright)",
    "frac_dim_cold": "Thin high cloud (cold + dim)", "btd_p50": "Night fog signal (11−3.7 µm)",
    "btd_p90": "Night fog signal, upper", "frac_btd_gt2": "Night fog area",
    "hour_sin": "Time of day", "hour_cos": "Time of day", "month_sin": "Season", "month_cos": "Season",
    "abs_scan": "Satellite view angle", "is_day": "Day / night",
    "d_bt_min_per_h": "Cloud-top cooling rate", "d_bt_min_100km_per_h": "Cooling rate within 100 km",
    "d_frac_lt_233_100km_per_h": "Growth of storm cloud area",
}


def roc(y, p):
    order = np.argsort(-np.asarray(p))
    y = np.asarray(y, bool)[order]
    tpr = np.concatenate([[0], np.cumsum(y) / max(y.sum(), 1)])
    fpr = np.concatenate([[0], np.cumsum(~y) / max((~y).sum(), 1)])
    return fpr, tpr

def pr(y, p):
    order = np.argsort(-np.asarray(p))
    y = np.asarray(y, bool)[order]
    tp = np.cumsum(y)
    return tp / max(y.sum(), 1), tp / np.arange(1, len(y) + 1)


# ── 1. How well v3 separates real events (ROC) ────────────────
def fig_roc(metrics, preds):
    events = [e for e in ("thunder_now", "rain_next3h", "rain_now", "fog_now") if e in preds]
    fig, axes = plt.subplots(1, len(events), figsize=(3.4 * len(events), 3.4), sharey=True)
    for ax, ev in zip(np.atleast_1d(axes), events):
        d, m = preds[ev], metrics["events"][ev]
        for p, color, ls, label in ((d["p"], NAVY, "-", f"v3  (AUC {m['auc']:.2f})"),
                                    (d["p_clim"], GREY, "--", f"Local history  (AUC {m['climatology_auc']:.2f})")):
            fpr, tpr = roc(d["y"], p)
            ax.plot(fpr, tpr, color=color, linestyle=ls, label=label)
        ax.plot([0, 1], [0, 1], color=GRID, linewidth=1)
        ax.set_title(EVENT_NAME[ev], fontsize=11, color=INK)
        ax.set_xlabel("False alarm rate")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1.01)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
    np.atleast_1d(axes)[0].set_ylabel("Share of real events caught")
    fig.suptitle(f"Out-of-year test: {metrics['events'][events[0]]['test_n']:,} predictions "
                 "(each year predicted by a model that never saw it)", fontsize=10, color=MUTED, y=1.03)
    fig.savefig(FIG_DIR / "1_roc_v3_vs_history.png")
    plt.close(fig)


# ── 2. Safety trade-off: catches vs. false alarms ─────────────
def fig_tradeoff(metrics, preds, ev="thunder_now"):
    d, m = preds[ev], metrics["events"][ev]
    rec, prec = pr(d["y"], d["p"])
    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    ax.plot(rec, prec, color=NAVY)
    base = np.mean(d["y"])
    ax.axhline(base, color=GREY, linestyle="--", linewidth=1.5)
    ax.text(0.02, base + 0.02, f"Random alerts would be right {base:.0%} of the time", ha="left",
            fontsize=8, color=MUTED)
    for key, label, color in (("best_f1", "Balanced setting", NAVY), ("safety", "Hiker-safety setting", ORANGE)):
        x = m[key]
        ax.plot(x["recall"], x["precision"], "o", markersize=8, color=color,
                markeredgecolor="white", markeredgewidth=2, zorder=5)
        ax.annotate(f"{label}\ncatches {x['recall']:.0%}, right {x['precision']:.0%} of the time",
                    (x["recall"], x["precision"]), xytext=(10, 10), textcoords="offset points",
                    fontsize=8, color=INK)
    ax.set_xlabel("Share of real thunderstorms caught")
    ax.set_ylabel("Share of alerts that were right")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_title(f"{EVENT_NAME[ev]}: the safety trade-off", fontsize=11, color=INK, loc="left")
    fig.savefig(FIG_DIR / "2_safety_tradeoff_thunder.png")
    plt.close(fig)


# ── 3. What v3 relies on ──────────────────────────────────────
def fig_importance(metrics, ev="thunder_now", top=10):
    feats = metrics["events"][ev]["top_features"][:top]
    names, vals = [], []
    for k, v in feats:
        n = FEATURE_NAME.get(k, k)
        if n in names:              # sin/cos pairs share a name
            vals[names.index(n)] += v
            continue
        names.append(n); vals.append(v)
    order = np.argsort(vals)
    fig, ax = plt.subplots(figsize=(5.6, 0.32 * len(names) + 1))
    ax.barh(np.array(names)[order], np.array(vals)[order], color=NAVY, height=0.6)
    ax.set_xlabel("Drop in accuracy when this input is scrambled")
    ax.set_title(f"What v3 relies on most — {EVENT_NAME[ev].lower()}", fontsize=11, color=INK, loc="left")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIG_DIR / f"3_feature_importance_{ev}.png")
    plt.close(fig)


# ── 4. Where the data comes from ──────────────────────────────
def fig_map():
    conn = sqlite3.connect(str(DB_PATH))
    counts = dict(conn.execute("SELECT location, COUNT(*) FROM samples GROUP BY location"))
    fig, ax = plt.subplots(figsize=(5.4, 6))
    for feat in json.loads(LAND_GEOJSON.read_text())["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = np.array(poly[0])
            if ring[:, 0].max() < 60 or ring[:, 0].min() > 100 or ring[:, 1].max() < 0 or ring[:, 1].min() > 40:
                continue
            ax.add_patch(Polygon(ring, closed=True, facecolor="#F2F2F2", edgecolor=GREY, linewidth=0.5))
    locs = locations()
    xs = [locs[k]["lon"] for k in counts]; ys = [locs[k]["lat"] for k in counts]
    n = np.array([counts[k] for k in counts])
    ax.scatter(xs, ys, s=12 + 180 * n / n.max(), color=NAVY, alpha=0.85,
               edgecolor="white", linewidth=1, zorder=3)
    label_at = {"VABB": (-8, 0, "right"), "VOHS": (8, 0, "left"), "VIDP": (8, 4, "left"),
                "VILH": (8, 2, "left"), "VISR": (-8, 2, "right"), "VISM": (8, -4, "left"),
                "VEGT": (6, -10, "left"), "VOTV": (8, -2, "left")}
    for k, (dx, dy, ha) in label_at.items():
        if k in counts:
            ax.annotate(f"{locs[k]['name'].title()} ({counts[k]:,})", (locs[k]["lon"], locs[k]["lat"]),
                        xytext=(dx, dy), textcoords="offset points", fontsize=7, color=INK,
                        ha=ha, va="center")
    ax.set_xlim(66, 98); ax.set_ylim(6, 37); ax.set_aspect("equal")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{sum(counts.values()):,} satellite–weather matches at {len(counts)} airports\n"
                 "(circle size = number of matches)", fontsize=10, color=INK, loc="left")
    fig.savefig(FIG_DIR / "4_map_of_samples.png")
    plt.close(fig)


# ── 6. Climb Risk Score: is the score honest? ─────────────────
def fig_reliability(risk):
    rel = risk["reliability"]
    x = [b["mean_score"] for b in rel]; y = [b["observed_rate_pct"] for b in rel]
    n = np.array([b["n"] for b in rel])
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.plot([0, 100], [0, 100], color=GREY, linestyle="--", linewidth=1.5)
    ax.text(62, 66, "Perfectly honest score", ha="center", fontsize=8, color=MUTED, rotation=45)
    ax.plot(x, y, color=NAVY, linewidth=1.5, zorder=2)
    ax.scatter(x, y, s=20 + 160 * n / n.max(), color=NAVY, edgecolor="white", linewidth=1.5, zorder=3)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("Climb Risk Score given")
    ax.set_ylabel("Hazard actually reported (%)")
    ax.set_title(f"Score calibration on years the model never saw\n"
                 f"({risk['test_n']:,} predictions; dot size = number of cases)",
                 fontsize=10, color=INK, loc="left", pad=12)
    fig.savefig(FIG_DIR / "6_risk_score_calibration.png")
    plt.close(fig)

def fig_bands(risk):
    bands = [b for b in risk["bands"] if b["n"] > 0]
    names = [f"{b['band'].title()}  ({b['score_range']})" for b in bands]
    rates = [b["observed_hazard_rate_pct"] for b in bands]
    fig, ax = plt.subplots(figsize=(5.6, 0.5 * len(bands) + 1.2))
    ax.barh(names, rates, color=NAVY, height=0.55)
    for k, b in enumerate(bands):
        ax.text(rates[k] + 1, k, f"{rates[k]:.0f}% had a hazard   ·   {b['share_of_cases_pct']:.0f}% of all cases",
                va="center", fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of cases in this band where a hazard was reported (%)")
    ax.set_title("Climb Risk bands — what actually happened", fontsize=11, color=INK, loc="left")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIG_DIR / "7_risk_bands.png")
    plt.close(fig)


# ── 5. Case studies on real passes ────────────────────────────
def pick_cases():
    """Thunderstorms reported in 2022–25 (out-of-year for the saved model):
    the strongest catch and the most confident miss."""
    with open(RESULTS_DIR / "model_v3.pkl", "rb") as f:
        models = pickle.load(f)
    m = models["thunder_now"]
    test_years = TEST_GROUPS[-1]
    data = build_dataset()
    add_cooling_features(data)
    set_climatology(data, test_years)
    rows = [r for r in data if r["time"].year in test_years and r["thunder_now"] is not None]
    p = m["model"].predict_proba(matrix(rows, m["features"]))[:, 1]
    t = m["thresholds"]["safety"]
    hits = [(pi, r) for pi, r in zip(p, rows) if r["thunder_now"] and pi >= t]
    misses = [(pi, r) for pi, r in zip(p, rows) if r["thunder_now"] and pi < t]
    cases = []
    if hits:
        cases.append(("caught",) + max(hits, key=lambda x: x[0]))
    if misses:
        cases.append(("missed",) + max(misses, key=lambda x: x[0]))
    return cases, t

def _risk_lookup():
    path = RESULTS_DIR / "risk_predictions_v3.json"
    if not path.exists():
        return {}
    d = json.loads(path.read_text())
    return {(m["obs_id"], m["location"]): sc for m, sc in zip(d["meta"], d["score"])}

def fig_case(kind, prob, r, threshold, idx, risk_scores=None):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    o = dict(conn.execute("SELECT * FROM observations WHERE obs_id=?", (r["obs_id"],)).fetchone())
    offsets, default = station_offsets()
    res = apt.process(o["image_path"])
    plat, plon, _ = geo.geolocate(TLE_NAME[o["satellite"]], o["tle1"], o["tle2"], o["start_utc"],
                                  res["n_lines"], step=1,
                                  time_offset_s=offsets.get(o["station_id"], default))
    loc = locations()[r["location"]]
    d = geo.R_EARTH * np.arccos(np.clip(np.sin(np.radians(loc["lat"])) * np.sin(np.radians(plat)) +
                                        np.cos(np.radians(loc["lat"])) * np.cos(np.radians(plat)) *
                                        np.cos(np.radians(plon - loc["lon"])), -1, 1))
    i, j = np.unravel_index(np.argmin(d), d.shape)
    w = 70
    rs, cs = slice(max(i - w, 0), i + w), slice(max(j - w, 0), j + w)
    bt = res["bt_b"][rs, cs]

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pcolormesh(plon[rs, cs], plat[rs, cs], bt, cmap="Greys", vmin=200, vmax=300, shading="auto")
    ax.contour(plon[rs, cs], plat[rs, cs], np.ma.masked_invalid(bt), levels=[233],
               colors=[ORANGE], linewidths=1.2)
    for feat in json.loads(LAND_GEOJSON.read_text())["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = np.array(poly[0])
            ax.plot(ring[:, 0], ring[:, 1], color=NAVY, linewidth=0.6)
    ax.plot(loc["lon"], loc["lat"], marker="^", markersize=10, color=NAVY,
            markeredgecolor="white", markeredgewidth=1.5)
    ax.set_xlim(plon[rs, cs].min(), plon[rs, cs].max())
    ax.set_ylim(plat[rs, cs].min(), plat[rs, cs].max())
    ax.set_aspect("equal"); ax.grid(False)
    ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    m = metar_window(r["location"], r["time"], 1, 1) or {}
    verdict = "CAUGHT" if kind == "caught" else "MISSED"
    ax.set_title(f"{verdict}: {loc['name'].title()}, {r['time']:%d %b %Y %H:%M} UTC\n"
                 f"{o['satellite']} infrared (white = cold cloud tops); orange outline = below −40 °C;\n"
                 f"white stripes = noisy lines removed",
                 fontsize=9, color=INK, loc="left")
    risk = (risk_scores or {}).get((r["obs_id"], r["location"]))
    risk_txt = f"   Climb Risk Score: {risk:.0f}/100 ({band_name(risk)})" if risk is not None else ""
    ax.text(0.0, -0.2, f"Airport reported: {'thunderstorm' if m.get('thunder') else '—'}"
            f"{', rain' if m.get('rain') else ''}.   v3 thunderstorm alert: "
            f"{'yes' if prob >= threshold else 'no'}.{risk_txt}",
            transform=ax.transAxes, fontsize=8, color=INK)
    fig.savefig(FIG_DIR / f"5_case_{idx}_{kind}_{r['location']}.png")
    plt.close(fig)
    return {"kind": kind, "location": loc["name"].title(), "time_utc": f"{r['time']:%Y-%m-%d %H:%M}",
            "satellite": o["satellite"], "thunder_alert": bool(prob >= threshold),
            "risk_score": None if risk is None else round(risk), "risk_band": band_name(risk),
            "observed": {k: bool(m.get(k)) for k in ("thunder", "rain", "fog")},
            "storm_dist_km": r["features"].get("storm_dist_km"),
            "coldest_100km_c": None if r["features"].get("bt_min_100km") is None
            else round(r["features"]["bt_min_100km"] - 273.15)}


def main():
    metrics = json.loads((RESULTS_DIR / "metrics_v3.json").read_text())
    preds = json.loads((RESULTS_DIR / "predictions_v3.json").read_text())
    fig_roc(metrics, preds)
    fig_tradeoff(metrics, preds)
    for ev in ("thunder_now", "rain_next3h"):
        if ev in metrics["events"] and "top_features" in metrics["events"][ev]:
            fig_importance(metrics, ev)
    fig_map()
    risk_path = RESULTS_DIR / "risk_v3.json"
    if risk_path.exists():
        risk = json.loads(risk_path.read_text())
        fig_reliability(risk)
        fig_bands(risk)
    cases, t = pick_cases()
    scores = _risk_lookup()
    info = [fig_case(kind, p, r, t, k + 1, scores) for k, (kind, p, r) in enumerate(cases)]
    (FIG_DIR / "cases.json").write_text(json.dumps(info, indent=1))
    print(f"[REPORT] Figures written to {FIG_DIR}")
    for f in sorted(FIG_DIR.glob("*.png")):
        print("  ", f.name)


if __name__ == "__main__":
    main()
