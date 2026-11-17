"""
Figures for the IRIS submission PDF (second edition).

    python -m archive.report_submission    # → data/archive/results/figures/sub_*.png
"""
import json
import sqlite3
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import DB_PATH
from archive.evaluate import RESULTS_DIR, confusion
from archive.report import FIG_DIR, NAVY, GREY, ORANGE, INK, MUTED, GRID, pr
from archive.landmask import is_land
from archive import apt, geo
from archive.process import TLE_NAME, station_offsets

PALE_NAVY = "#E8EDF3"
PALE_ORANGE = "#FDEEE8"
plt.rcParams["axes.axisbelow"] = True


# ── helpers for drawn diagrams ────────────────────────────────
def box(ax, x, y, w, h, title, lines=(), kind="plain", title_size=10.5):
    fc, ec, lw = {"plain": ("white", NAVY, 1.1), "accent": (PALE_ORANGE, ORANGE, 1.6),
                  "input": (PALE_NAVY, GREY, 1.0), "phase": ("none", GREY, 0.8)}[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08",
                                facecolor=fc, edgecolor=ec, linewidth=lw,
                                linestyle="--" if kind == "input" else "-"))
    if lines:
        ax.text(x + w / 2, y + h - 0.2, title, ha="center", va="top", fontsize=title_size,
                weight="bold", color=NAVY)
        ax.text(x + w / 2, y + h - 0.78, "\n".join(lines), ha="center", va="top", fontsize=8,
                color=INK, linespacing=1.35)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=title_size,
                weight="bold", color=NAVY)

def arrow(ax, x0, y0, x1, y1, color=MUTED, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=11,
                                 color=color, linewidth=1.1, linestyle=ls, shrinkA=0, shrinkB=0))


# ── 1. Algorithm flow chart ───────────────────────────────────
def fig_algorithm():
    fig, ax = plt.subplots(figsize=(11, 9.6))
    ax.set_xlim(0, 22); ax.set_ylim(0, 19.2); ax.axis("off")
    W, H = 4.2, 1.9
    xs = [2.6, 7.3, 12.0, 16.7]
    phases = [("1  RECEIVE AND DECODE", 16.2), ("2  CLEAN AND CALIBRATE", 12.6),
              ("3  MAP AND MEASURE", 9.0), ("4  PREDICT AND WARN", 5.4)]
    for name, y in phases:
        ax.add_patch(Rectangle((0.3, y - 0.35), 21.4, H + 0.7, facecolor="#FAFAFA", edgecolor="none"))
        num, word = name.split("  ", 1)
        short = {"RECEIVE AND DECODE": "RECEIVE", "CLEAN AND CALIBRATE": "CALIBRATE",
                 "MAP AND MEASURE": "MEASURE", "PREDICT AND WARN": "DECIDE"}[word]
        ax.text(1.4, y + H / 2 + 0.35, num, fontsize=15, weight="bold", color=ORANGE, va="center", ha="center")
        ax.text(1.4, y + H / 2 - 0.45, short, fontsize=7.5, weight="bold", color=MUTED, va="center", ha="center")
    rows = [
        [("Pass prediction", ["Orbit data (TLE) + SGP4", "forecast the next pass", "over the user"]),
         ("137 MHz antenna", ["Radio records the", "APT signal for", "10–15 minutes"]),
         ("Demodulate", ["Audio tone amplitude", "→ brightness,", "4,160 values per second"]),
         ("Image lines", ["2 lines per second,", "2,080 values each:", "two channels side by side"])],
        [("Align lines", ["Find the 7-pulse", "1,040 Hz sync on", "every line"]),
         ("Reject noise", ["Drop lines with a rough", "space-view strip;", "3×3 median filter"]),
         ("Calibrate", ["Grey wedges 1–9 fix", "the scale; wedge 16", "names the channel"]),
         ("Temperature", ["Deep space + warm", "target + Planck's law", "→ cloud tops in K"])],
        [("Georeference", ["Orbit + scan geometry", "place all 909 pixels", "per line on the map"]),
         ("Coastline check", ["Real coastlines", "confirm position;", "timing offset 8 s"]),
         ("User position", ["GPS fix of the", "trekker (airport", "in this study)"]),
         ("46 inputs", ["Cold tops, storm", "structure, brightness,", "fog signal, cooling"])],
        [("Hazard models", ["Gradient-boosted", "trees: thunder, rain", "now, rain 3 h, fog"]),
         ("Risk model", ["Any-hazard chance,", "calibrated so 30", "means about 30%"]),
         ("Safety rules", ["Storm cloud within", "20 km or overshooting", "top → at least High"]),
         ("Climb Risk Score", ["0–100 + band + advice", "+ reasons on screen;", "No data / Stale flags"])],
    ]
    for (pname, y), row in zip(phases, rows):
        for i, (x, (t, lines)) in enumerate(zip(xs, row)):
            kind = "accent" if (pname.startswith("4") and i == 3) else "plain"
            box(ax, x, y, W, H, t, lines, kind)
            if i < 3:
                arrow(ax, x + W + 0.05, y + H / 2, xs[i + 1] - 0.05, y + H / 2)
    # snake connectors between phases
    for (_, y0), (_, y1) in zip(phases[:-1], phases[1:]):
        arrow(ax, xs[3] + W / 2, y0 - 0.05, xs[3] + W / 2, y0 - 0.55, style="-")
        ax.plot([xs[3] + W / 2, xs[0] + W / 2], [y0 - 0.55, y0 - 0.55], color=MUTED, lw=1.1)
        arrow(ax, xs[0] + W / 2, y0 - 0.55, xs[0] + W / 2, y1 + H + 0.05)
    # side inputs
    box(ax, 2.6, 1.3, 4.2, 1.6, "Airport history", ["How often hazards are", "reported here by season"], "input", 9.5)
    box(ax, 7.3, 1.3, 4.2, 1.6, "Previous pass", ["Cloud-top change over 4 h;", "cooling = growing storm"], "input", 9.5)
    box(ax, 12.0, 1.3, 4.2, 1.6, "Training data", ["5,808 real satellite–", "weather cases, 2020–2025"], "input", 9.5)
    box(ax, 16.7, 1.3, 4.2, 1.6, "Trekker", ["Reads band, advice and", "reasons; decides go/no-go"], "input", 9.5)
    arrow(ax, 4.7, 2.9, 4.7, 5.35, color=GREY, ls="--")
    arrow(ax, 9.4, 2.9, 9.4, 5.35, color=GREY, ls="--")
    arrow(ax, 14.1, 2.9, 14.1, 5.35, color=GREY, ls="--")
    arrow(ax, 18.8, 5.35, 18.8, 2.95, color=ORANGE)
    ax.text(1.4, 2.1, "INPUTS", fontsize=7.5, weight="bold", color=MUTED, va="center", ha="center")
    ax.text(0.3, 18.85, "TrailSky algorithm: from a satellite pass overhead to a Climb Risk Score",
            fontsize=14, color=INK, weight="bold")
    fig.savefig(FIG_DIR / "sub_01_algorithm.png", dpi=170)
    plt.close(fig)


# ── 2. Training and test design ───────────────────────────────
def fig_split():
    fig, ax = plt.subplots(figsize=(11, 6.6))
    ax.set_xlim(0, 22); ax.set_ylim(0, 13.2); ax.axis("off")
    ax.text(0.3, 12.75, "Training and test design: the model never sees 2019 until the final test",
            fontsize=14, weight="bold", color=INK)
    years = [(2019, 2860, "test"), (2020, 880, "tuning"), (2021, 4559, "training"), (2022, 7, "training"),
             (2023, 88, "training"), (2024, 3, "training"), (2025, 271, "training")]
    x, top = 0.6, 11.6
    bw = 2.75
    for i, (yr, n, role) in enumerate(years):
        xi = x + i * (bw + 0.35)
        kind = "accent" if role == "test" else "input" if role == "tuning" else "plain"
        box(ax, xi, top - 1.9, bw, 1.9, str(yr), [f"{n:,} cases", role], kind, 11)
        # size bar under each year
        h = 1.6 * np.sqrt(n / 4559)
        ax.add_patch(Rectangle((xi + bw / 2 - 0.35, top - 2.2 - h), 0.7, h,
                               facecolor=ORANGE if role == "test" else NAVY, edgecolor="none", alpha=0.85))
    ax.text(0.6, 7.45, "bar area ∝ number of cases", fontsize=7.5, color=MUTED)
    # training bracket
    x0, x1 = 0.6 + 1 * (bw + 0.35), 0.6 + 6 * (bw + 0.35) + bw
    ax.plot([x0, x1], [7.2, 7.2], color=NAVY, lw=1.2)
    ax.plot([x0, x0], [7.2, 7.45], color=NAVY, lw=1.2); ax.plot([x1, x1], [7.2, 7.45], color=NAVY, lw=1.2)
    arrow(ax, (x0 + x1) / 2, 7.2, (x0 + x1) / 2, 6.3, color=NAVY)
    box(ax, 4.2, 4.4, 9.2, 1.9, "Train", ["Hazard models + Climb Risk model, 5,808 cases",
                                          "Settings and calibration from 2020 (880 cases)"], "plain", 11)
    box(ax, 14.4, 4.4, 6.9, 1.9, "Lock the model", ["Settings, thresholds and safety", "floors fixed before any 2019 case"], "plain", 11)
    arrow(ax, 13.45, 5.35, 14.35, 5.35)
    # locked model feeds the single prediction
    ax.plot([17.85, 17.85], [4.35, 3.25], color=NAVY, lw=1.1)
    ax.plot([17.85, 8.8], [3.25, 3.25], color=NAVY, lw=1.1)
    arrow(ax, 8.8, 3.25, 8.8, 2.45, color=NAVY)
    ax.text(13.3, 3.4, "locked model", fontsize=8.5, color=NAVY, ha="center")
    # held-out test path
    tx = 0.6 + bw / 2
    ax.plot([tx, tx], [7.4, 1.45], color=ORANGE, lw=1.4, linestyle="--")
    ax.text(tx + 0.18, 4.6, "held out until the end", fontsize=8.5, color=ORANGE, rotation=90, va="center")
    arrow(ax, tx, 1.45, 4.15, 1.45, color=ORANGE)
    box(ax, 4.2, 0.5, 9.2, 1.9, "Predict 2019 once", ["2,860 cases never seen in training,",
                                                       "each compared with the airport's report"], "accent", 11)
    arrow(ax, 13.45, 1.45, 14.35, 1.45)
    box(ax, 14.4, 0.5, 6.9, 1.9, "Result", ["Thunderstorm AUC 0.90", "vs 0.81 for local history"], "plain", 11)
    fig.savefig(FIG_DIR / "sub_02_train_test.png", dpi=170)
    plt.close(fig)


# ── 3. Anatomy of a real APT image ────────────────────────────
def fig_apt_anatomy(obs_id=12120715):
    conn = sqlite3.connect(str(DB_PATH))
    path = conn.execute("SELECT image_path FROM observations WHERE obs_id=?", (obs_id,)).fetchone()[0]
    img = np.array(Image.open(path).convert("L"))
    live = img.max(axis=1) > 0
    img = img[:np.where(live)[0].max() + 1]
    aligned, _, _ = apt.align_lines(img)
    crop = aligned[150:1050]
    fig = plt.figure(figsize=(11, 6.8))
    ax = fig.add_axes([0.02, 0.06, 0.70, 0.80])
    ax.imshow(crop, cmap="gray", aspect="auto", vmin=0, vmax=255)
    ax.set_xticks([]); ax.set_yticks([])
    parts = [(0, 39, "Sync A"), (39, 86, "Space A"), (86, 995, "Image A: visible light (day)"),
             (995, 1040, "Telemetry A"), (1040, 1079, "Sync B"), (1079, 1126, "Space B"),
             (1126, 2035, "Image B: thermal infrared, 10.8 µm"), (2035, 2080, "Telemetry B")]
    rows = {"Sync A": -52, "Space A": -92, "Telemetry A": -52, "Sync B": -92, "Space B": -132,
            "Telemetry B": -52}
    for k, (a, b, name) in enumerate(parts):
        y = rows.get(name, -12)
        ax.annotate("", xy=(a, y + 8), xytext=(b, y + 8), annotation_clip=False,
                    arrowprops=dict(arrowstyle="|-|", color=NAVY, lw=0.9, mutation_scale=3))
        ax.text((a + b) / 2, y - 4, name, ha="center", va="bottom", fontsize=7.5, color=NAVY,
                clip_on=False)
    ax.set_ylim(len(crop), -165)
    # zoom on telemetry wedges
    axz = fig.add_axes([0.75, 0.06, 0.23, 0.80])
    wedge = aligned[300:300 + 256, 2035 - 120:2080]
    axz.imshow(wedge, cmap="gray", aspect="auto", vmin=0, vmax=255)
    axz.set_xticks([]); axz.set_yticks([])
    axz.set_title("Zoom: Image B edge and\nits telemetry wedges", fontsize=8.5, color=INK)
    for k, lab in ((0, "wedges 1–8: grey steps"), (8, "wedge 9: zero"), (14, "wedge 15: warm target"),
                   (15, "wedge 16: channel ID")):
        pass
    fig.text(0.02, 0.92, "Anatomy of a real APT pass: NOAA-19 over India, 7 August 2025 (recorded near Bangalore)",
             fontsize=12.5, weight="bold", color=INK)
    fig.text(0.02, 0.015, "Each image row is one line sent by the satellite (2 per second). Vertical stripes at the "
             "edges are the sync pulses, space views and calibration wedges that make calibration possible.",
             fontsize=8, color=MUTED)
    fig.savefig(FIG_DIR / "sub_03_apt_anatomy.png", dpi=170)
    plt.close(fig)


# ── 4. Georeferencing check: before and after ─────────────────
def _geolocate_scan_angle(satellite, tle1, tle2, start_utc, n_lines):
    """The first (wrong) model: pixels evenly spaced in scan angle."""
    lat, lon, alt, heading, _ = geo.track(satellite, tle1, tle2, start_utc, n_lines)
    theta = (geo.PIXELS // 2 - np.arange(geo.PIXELS)) / (geo.PIXELS // 2) * geo.SCAN_HALF_ANGLE
    h = alt.mean()
    gamma = np.arcsin(np.clip((geo.R_EARTH + h) / geo.R_EARTH * np.sin(np.abs(theta)), -1, 1)) - np.abs(theta)
    side = np.where(theta >= 0, np.pi / 2, -np.pi / 2)
    plat, plon = geo._destination(lat[:, None], lon[:, None], heading[:, None] + side[None, :],
                                  (geo.R_EARTH * gamma)[None, :])
    return np.degrees(plat), np.degrees(plon)

def fig_georef(obs_id=12120715):
    from scipy.ndimage import binary_erosion
    conn = sqlite3.connect(str(DB_PATH)); conn.row_factory = sqlite3.Row
    o = dict(conn.execute("SELECT * FROM observations WHERE obs_id=?", (obs_id,)).fetchone())
    r = apt.process(o["image_path"])
    a = np.nan_to_num(r["image_a"], nan=0)
    offsets, default = station_offsets()
    off = offsets.get(o["station_id"], default)
    la0, lo0 = _geolocate_scan_angle(TLE_NAME[o["satellite"]], o["tle1"], o["tle2"], o["start_utc"], r["n_lines"])
    la1, lo1, _ = geo.geolocate(TLE_NAME[o["satellite"]], o["tle1"], o["tle2"], o["start_utc"],
                                r["n_lines"], step=1, time_offset_s=off)
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.6))
    for ax, (la, lo), title in ((axes[0], (la0, lo0), "Before: pixels spaced by scan angle\n(India drawn ~40% too wide)"),
                                (axes[1], (la1, lo1), f"After: spaced by ground distance\n+ {off:.0f} s timing offset (coast lines up)")):
        land = is_land(la, lo); edge = land & ~binary_erosion(land)
        rgb = np.stack([a] * 3, -1).astype(np.uint8)
        rgb[edge] = [232, 93, 38]
        ax.imshow(rgb[60:1000], aspect="auto")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10.5, color=INK)
    fig.suptitle("Checking the map position against real coastlines (orange) on a real NOAA-19 pass, 7 Aug 2025",
                 fontsize=12, weight="bold", color=INK, x=0.02, ha="left", y=0.99)
    fig.text(0.02, 0.01, "Visible-light channel; land is brighter than sea. The orange line is where the software "
             "believes the coast is.", fontsize=8, color=MUTED)
    fig.savefig(FIG_DIR / "sub_04_georef_check.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


# ── 5. Safety trade-off on the 2019 test year ─────────────────
def fig_tradeoff_2019():
    preds = json.loads((RESULTS_DIR / "predictions_v3.json").read_text())
    metrics = json.loads((RESULTS_DIR / "metrics_v3.json").read_text())
    d = preds["thunder_now"]
    k = np.array(d["group"]) == "2018-2019"
    y, p = np.array(d["y"], bool)[k], np.array(d["p"])[k]
    fold = [f for f in metrics["events"]["thunder_now"]["folds"] if f["test_years"] == [2018, 2019]][0]
    rec, prec = pr(y, p)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot(rec, prec, color=NAVY)
    base = y.mean()
    ax.axhline(base, color=GREY, linestyle="--", linewidth=1.5)
    ax.text(0.02, base + 0.02, f"Random alerts would be right {base:.0%} of the time", fontsize=8, color=MUTED)
    for key, label, color in (("best_f1", "Balanced setting", NAVY), ("safety", "Hiker-safety setting", ORANGE)):
        c = confusion(y, p >= fold["thresholds"][key])
        ax.plot(c["recall"], c["precision"], "o", markersize=9, color=color, markeredgecolor="white",
                markeredgewidth=2, zorder=5)
        ax.annotate(f"{label}\ncatches {c['recall']:.0%}, right {c['precision']:.0%}",
                    (c["recall"], c["precision"]), xytext=(12, 10), textcoords="offset points", fontsize=8.5, color=INK)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("Share of real thunderstorms caught"); ax.set_ylabel("Share of alerts that were right")
    ax.set_title("Thunderstorm alerts on the 2019 test year: catching more costs false alarms",
                 fontsize=10.5, color=INK, loc="left")
    fig.savefig(FIG_DIR / "sub_05_tradeoff_2019.png", dpi=170)
    plt.close(fig)


# ── 6. Equations rendered as images ───────────────────────────
EQUATIONS = {
    "eq_radiance": r"$R \;=\; R_{\mathrm{bb}}\,\dfrac{C_{\mathrm{space}} - C}{C_{\mathrm{space}} - C_{\mathrm{bb}}}$",
    "eq_planck": r"$T \;=\; \dfrac{c_2\,\nu}{\ln\!\left(1 + \dfrac{c_1\,\nu^{3}}{R}\right)}$",
    "eq_auc": r"$\mathrm{AUC} \;=\; P\left(\,s_{\mathrm{hazard}} > s_{\mathrm{calm}}\,\right)$",
    "eq_brier": r"$B \;=\; \dfrac{1}{N}\sum_{i=1}^{N}\left(p_i - o_i\right)^{2}$",
    "eq_skill": r"$\mathrm{Skill} \;=\; 1 - \dfrac{B_{\mathrm{TrailSky}}}{B_{\mathrm{history}}}$",
}
EQ_DPI = 300

def render_equations():
    with plt.rc_context({"mathtext.fontset": "stix", "font.family": "STIXGeneral"}):
        for name, tex in EQUATIONS.items():
            fig = plt.figure(figsize=(6, 1.2))
            fig.text(0.5, 0.5, tex, ha="center", va="center", fontsize=14, color=INK)
            fig.savefig(FIG_DIR / f"{name}.png", dpi=EQ_DPI, bbox_inches="tight", pad_inches=0.04,
                        facecolor="white")
            plt.close(fig)


def main():
    fig_algorithm()
    fig_split()
    fig_apt_anatomy()
    fig_georef()
    fig_tradeoff_2019()
    render_equations()
    for f in sorted(FIG_DIR.glob("sub_*.png")) + sorted(FIG_DIR.glob("eq_*.png")):
        print("  ", f.name)


if __name__ == "__main__":
    main()
