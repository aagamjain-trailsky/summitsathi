"""
Figures for the IRIS submission: the 2019 test year, the dataset funnel,
the training/test split and the algorithm flow chart.

    python -m archive.report_iris     # → data/archive/results/figures/iris_*.png
"""
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.evaluate import RESULTS_DIR
from archive.report import roc, FIG_DIR, NAVY, GREY, ORANGE, INK, MUTED, GRID, EVENT_NAME

TEST_GROUP = "2018-2019"


def compute_test_2019():
    """Results for the 2019 test year (the fold that held out 2018-2019), saved
    to results/test_2019.json for the figures and the submission text."""
    from archive.evaluate import auc, confusion, bootstrap_f1
    metrics = json.loads((RESULTS_DIR / "metrics_v3.json").read_text())
    preds = json.loads((RESULTS_DIR / "predictions_v3.json").read_text())
    rpred = json.loads((RESULTS_DIR / "risk_predictions_v3.json").read_text())
    out = {}
    for ev in ("thunder_now", "rain_next3h", "rain_now", "fog_now"):
        d = preds[ev]
        k = np.array(d["group"]) == TEST_GROUP
        y, p = np.array(d["y"], bool)[k], np.array(d["p"])[k]
        fold = [f for f in metrics["events"][ev]["folds"] if f["test_years"] == [2018, 2019]][0]
        cs, cb = confusion(y, p >= fold["thresholds"]["safety"]), confusion(y, p >= fold["thresholds"]["best_f1"])
        out[ev] = dict(n=int(k.sum()), events=int(y.sum()), auc=auc(y, p),
                       sat=auc(y, np.array(d["p_sat"])[k]), clim=auc(y, np.array(d["p_clim"])[k]),
                       safe_rec=cs["recall"], safe_prec=cs["precision"], bal_rec=cb["recall"],
                       bal_prec=cb["precision"], bal_f1=cb["f1"],
                       bal_ci=bootstrap_f1(y, p >= fold["thresholds"]["best_f1"]))
    k = np.array(rpred["group"]) == TEST_GROUP
    s, y, b = np.array(rpred["score"])[k], np.array(rpred["y"], bool)[k], np.array(rpred["baseline"])[k]
    bands = []
    for lo, hi, name in [(0, 10, "Minimal"), (10, 25, "Low"), (25, 45, "Moderate"), (45, 70, "High"), (70, 101, "Extreme")]:
        q = (s >= lo) & (s < hi)
        bands.append(dict(band=name, lo=lo, hi=min(hi, 100), n=int(q.sum()), share=float(q.mean()),
                          hazard=float(y[q].mean()) if q.sum() else None))
    risk = dict(n=int(k.sum()), rate=float(y.mean()), auc=auc(y, s), brier=float(((s / 100 - y) ** 2).mean()),
                brier_clim=float(((b / 100 - y) ** 2).mean()), bands=bands)
    result = {"test_year": 2019, "events": out, "risk": risk}
    (RESULTS_DIR / "test_2019.json").write_text(json.dumps(result, indent=1, default=float))
    return result


def test_slice(d, key):
    k = np.array(d["group"]) == TEST_GROUP
    return np.array(d[key])[k]


def fig_roc_2019(preds, test):
    events = ["thunder_now", "rain_next3h", "rain_now", "fog_now"]
    fig, axes = plt.subplots(1, 4, figsize=(13.6, 3.4), sharey=True)
    for ax, ev in zip(axes, events):
        d, e = preds[ev], test["events"][ev]
        y = test_slice(d, "y")
        for p, color, ls, label in ((test_slice(d, "p"), NAVY, "-", f"v3  (AUC {e['auc']:.2f})"),
                                    (test_slice(d, "p_clim"), GREY, "--", f"Local history  (AUC {e['clim']:.2f})")):
            fpr, tpr = roc(y, p)
            ax.plot(fpr, tpr, color=color, linestyle=ls, label=label)
        ax.plot([0, 1], [0, 1], color=GRID, linewidth=1)
        ax.set_title(f"{EVENT_NAME[ev]}  ({e['events']} cases)", fontsize=10.5, color=INK)
        ax.set_xlabel("False alarm rate")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1.01)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
    axes[0].set_ylabel("Share of real events caught")
    fig.suptitle(f"2019 test year: {test['events']['thunder_now']['n']:,} cases the model never saw",
                 fontsize=10, color=MUTED, y=1.03)
    fig.savefig(FIG_DIR / "iris_1_test2019_detection.png")
    plt.close(fig)


def fig_bands_2019(test):
    bands = [b for b in test["risk"]["bands"] if b["n"]]
    names = [f"{b['band']}  ({b['lo']}–{b['hi']})" for b in bands]
    rates = [100 * b["hazard"] for b in bands]
    fig, ax = plt.subplots(figsize=(5.8, 0.5 * len(bands) + 1.3))
    ax.barh(names, rates, color=NAVY, height=0.55)
    for k, b in enumerate(bands):
        ax.text(rates[k] + 1, k, f"{rates[k]:.0f}% had a hazard  ·  {b['n']:,} cases",
                va="center", fontsize=8, color=INK)
    ax.invert_yaxis(); ax.set_xlim(0, 100); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Cases in this band where a hazard was reported (%)")
    ax.set_title("Climb Risk bands on the 2019 test year", fontsize=11, color=INK, loc="left")
    fig.savefig(FIG_DIR / "iris_2_test2019_risk_bands.png")
    plt.close(fig)


def fig_calibration_2019(rpred, test):
    k = np.array(rpred["group"]) == TEST_GROUP
    s, y = np.array(rpred["score"])[k], np.array(rpred["y"], bool)[k]
    edges = [0, 10, 20, 30, 45, 60, 80, 101]
    xs, ys, ns = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (s >= lo) & (s < hi)
        if m.sum() >= 15:
            xs.append(s[m].mean()); ys.append(100 * y[m].mean()); ns.append(m.sum())
    ns = np.array(ns)
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.plot([0, 100], [0, 100], color=GREY, linestyle="--", linewidth=1.5)
    ax.text(62, 66, "Perfectly honest score", ha="center", fontsize=8, color=MUTED, rotation=45)
    ax.plot(xs, ys, color=NAVY, linewidth=1.5)
    ax.scatter(xs, ys, s=20 + 160 * ns / ns.max(), color=NAVY, edgecolor="white", linewidth=1.5, zorder=3)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("Climb Risk Score given"); ax.set_ylabel("Hazard actually reported (%)")
    ax.set_title(f"Score calibration, 2019 test year\n({k.sum():,} cases; dot size = number of cases; "
                 "bins with 15+ cases)", fontsize=9.5, color=INK, loc="left", pad=10)
    fig.savefig(FIG_DIR / "iris_3_test2019_calibration.png")
    plt.close(fig)


def fig_funnel():
    stages = [("Passes found on SatNOGS", 1623), ("Downloaded", 1616),
              ("From stations recording real images", 1425), ("Clean enough to use", 677),
              ("With an airport in the clean part", 625)]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, (name, n) in enumerate(stages):
        ax.barh(i, n, color=NAVY if i == len(stages) - 1 else GREY, height=0.6)
        ax.text(n + 20, i, f"{n:,}", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(stages)), [s for s, _ in stages])
    ax.invert_yaxis(); ax.set_xlim(0, 1900); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Satellite passes")
    ax.set_title("From 1,623 passes to 625 usable ones (11,156 airport matches)",
                 fontsize=10.5, color=INK, loc="left")
    fig.savefig(FIG_DIR / "iris_4_data_funnel.png")
    plt.close(fig)


def fig_split():
    years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
    reported = [2860, 880, 4559, 7, 88, 3, 271]
    colors = [ORANGE if y == 2019 else NAVY for y in years]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    bars = ax.bar([str(y) for y in years], reported, color=colors, width=0.6)
    for b, n, y in zip(bars, reported, years):
        label = f"{n:,}" + ("\ntest" if y == 2019 else "\ntuning" if y == 2020 else "")
        ax.text(b.get_x() + b.get_width() / 2, n + 60, label, ha="center", fontsize=8, color=INK)
    ax.set_ylim(0, 5300); ax.grid(axis="x", visible=False)
    ax.set_ylabel("Data points with an airport report")
    ax.set_title("Training on every year except 2019 (5,808), testing on 2019 (2,860)",
                 fontsize=10.5, color=INK, loc="left")
    fig.savefig(FIG_DIR / "iris_5_train_test_split.png")
    plt.close(fig)


def fig_flowchart():
    steps = [("Receive", "NOAA satellite passes overhead;\nradio records the 137 MHz APT signal"),
             ("Clean", "Align each line on its sync pulse;\ndrop noisy lines; remove speckle"),
             ("Calibrate", "Grey wedges + deep space + warm target\n→ cloud-top temperature (K)"),
             ("Georeference", "Orbit (TLE + SGP4) places every pixel;\nchecked against real coastlines"),
             ("Measure", "46 inputs around the user's position:\ncold tops, storm structure, fog, cooling"),
             ("Predict", "Gradient-boosted trees, one per hazard:\nthunderstorm, rain now, rain in 3 h, fog"),
             ("Score", "Calibrated Climb Risk Score 0–100\n+ safety rules (storm within 20 km → High)"),
             ("Warn", "Band, advice and reasons on screen;\nNo data / Stale when the view is missing or old")]
    fig, ax = plt.subplots(figsize=(7.2, 10.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, len(steps) * 1.25 + 0.4); ax.axis("off")
    for i, (name, text) in enumerate(steps):
        y = len(steps) * 1.25 - i * 1.25 - 0.6
        main = name in ("Score", "Warn")
        ax.add_patch(FancyBboxPatch((0.4, y - 0.42), 9.2, 0.84, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    facecolor="#FDEEE8" if main else "white",
                                    edgecolor=ORANGE if main else NAVY, linewidth=1.6 if main else 1.2))
        ax.text(0.75, y, name, fontsize=12, weight="bold", color=NAVY, va="center")
        ax.text(3.45, y, text, fontsize=9.5, color=INK, va="center", linespacing=1.4)
        if i < len(steps) - 1:
            ax.annotate("", xy=(5, y - 0.79), xytext=(5, y - 0.45),
                        arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.2))
    ax.set_title("TrailSky: from satellite signal to Climb Risk Score", fontsize=13, color=INK, loc="left")
    fig.savefig(FIG_DIR / "iris_6_algorithm_flowchart.png")
    plt.close(fig)


def main():
    plt.rcParams["axes.axisbelow"] = True
    preds = json.loads((RESULTS_DIR / "predictions_v3.json").read_text())
    rpred = json.loads((RESULTS_DIR / "risk_predictions_v3.json").read_text())
    test = compute_test_2019()
    fig_roc_2019(preds, test)
    fig_bands_2019(test)
    fig_calibration_2019(rpred, test)
    fig_funnel()
    fig_split()
    fig_flowchart()
    for f in sorted(FIG_DIR.glob("iris_*.png")):
        print("  ", f.name)


if __name__ == "__main__":
    main()
