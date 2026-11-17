"""
Figures for the product explainer (Meteor-M LRPT version of SummitSathi).

    python -m archive.report_product <tle_file>   # → data/archive/results/figures/prod_*.png
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pyorbital.orbital import Orbital
from pyorbital.astronomy import observer_position

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.report import FIG_DIR, NAVY, GREY, ORANGE, INK, MUTED
from archive.report_submission import box, arrow, PALE_NAVY, PALE_ORANGE

C_LIGHT = 299792.458  # km/s
PLACE = ("Manali", 32.24, 77.19, 2.0)   # name, lat, lon, altitude km


def read_tles(path):
    lines = [l.rstrip() for l in Path(path).read_text().splitlines() if l.strip()]
    out = {}
    for i in range(0, len(lines) - 2, 3):
        out[lines[i].strip()] = (lines[i + 1], lines[i + 2])
    return out


# ── 1. System overview ────────────────────────────────────────
def fig_system():
    fig, ax = plt.subplots(figsize=(11, 7.4))
    ax.set_xlim(0, 22); ax.set_ylim(0, 14.8); ax.axis("off")
    ax.text(0.3, 14.35, "Inside SummitSathi: from the satellite overhead to the warning on screen",
            fontsize=14, weight="bold", color=INK)
    # sky
    box(ax, 0.6, 11.0, 5.6, 2.4, "Meteor-M satellite", ["~830 km up, 98.6° polar orbit", "MSU-MR camera, 6 channels",
                                                         "LRPT broadcast at 137 MHz"], "accent", 10.5)
    arrow(ax, 6.25, 12.2, 7.55, 12.2, color=ORANGE)
    ax.text(6.9, 12.45, "radio\nwaves", fontsize=7.5, color=ORANGE, ha="center")
    # RF chain
    box(ax, 7.6, 11.0, 4.0, 2.4, "Antenna", ["137 MHz, circularly", "polarised (QFH or", "V-dipole)"])
    arrow(ax, 11.65, 12.2, 12.55, 12.2)
    box(ax, 12.6, 11.0, 4.0, 2.4, "Filter + LNA", ["Blocks FM radio;", "boosts the weak", "signal near antenna"])
    arrow(ax, 16.65, 12.2, 17.55, 12.2)
    box(ax, 17.6, 11.0, 4.0, 2.4, "SDR receiver", ["Tunes to 137 MHz;", "digitises the signal", "into I/Q samples"])
    # computer
    ax.add_patch(plt.Rectangle((0.6, 3.3), 21.0, 6.9, facecolor="#FAFAFA", edgecolor=NAVY, linewidth=1.2))
    ax.text(0.9, 9.75, "ON-BOARD COMPUTER (runs all software in the field, no internet needed)",
            fontsize=8.5, weight="bold", color=NAVY)
    arrow(ax, 19.6, 10.95, 19.6, 9.25)
    row1 = [(17.6, "Demodulate", ["QPSK signal → bits"]), (12.6, "Decode", ["Error correction →", "data packets"]),
            (7.6, "Rebuild image", ["JPEG blocks →", "3 image channels"]), (2.6, "Physics", ["Pixel values →", "cloud-top temperature"])]
    for i, (x, t, l) in enumerate(row1):
        box(ax, x, 7.0, 4.0, 2.2, t, l, "plain", 10)
        if i < len(row1) - 1:
            arrow(ax, x - 0.05, 8.1, row1[i + 1][0] + 4.05, 8.1)
    row2 = [(2.6, "Map", ["Orbit → latitude and", "longitude of each pixel"]),
            (8.0, "Measure", ["46 inputs around the", "trekker's GPS position"]),
            (13.4, "Predict + score", ["Hazard models, Climb", "Risk 0–100, safety rules"])]
    arrow(ax, 4.6, 6.95, 4.6, 6.25)
    for i, (x, t, l) in enumerate(row2):
        box(ax, x, 4.0, 4.0, 2.2, t, l, "accent" if i == 2 else "plain", 10)
        if i < len(row2) - 1:
            arrow(ax, x + 4.05, 5.1, row2[i + 1][0] - 0.05, 5.1)
    # peripherals, each under the step it feeds
    box(ax, 2.3, 0.3, 4.6, 2.3, "Stored data", ["Orbit data (TLE), trained", "models, local history"], "input", 10)
    arrow(ax, 4.6, 2.65, 4.6, 3.95, color=GREY, ls="--")
    box(ax, 7.7, 0.3, 4.6, 2.3, "GPS + clock", ["Where the trekker is;", "exact time for orbits"], "input", 10)
    arrow(ax, 10.0, 2.65, 10.0, 3.95, color=GREY, ls="--")
    box(ax, 13.1, 0.3, 4.6, 2.3, "Screen", ["Score, band, advice,", "reasons, next pass"], "accent", 10)
    arrow(ax, 15.4, 3.95, 15.4, 2.65, color=ORANGE)
    box(ax, 18.3, 0.3, 3.3, 2.3, "Battery", ["Powers every", "part all day"], "input", 10)
    fig.savefig(FIG_DIR / "prod_01_system.png", dpi=170)
    plt.close(fig)


# ── 2. Decoding stack ─────────────────────────────────────────
def fig_decode():
    layers = [
        ("Radio wave", "137 MHz carrier, phase-modulated (QPSK); about 140 kHz wide; shifted up to ±3 kHz by Doppler"),
        ("I/Q samples", "SDR mixes the signal down and samples it ~1–2 million times a second (in-phase + quadrature)"),
        ("Symbols", "Demodulator locks to the carrier and symbol clock; each symbol = one of 4 phases = 2 bits"),
        ("Soft bits", "72 kbit/s stream of 'probably 0 / probably 1' values, about half of them redundancy"),
        ("Viterbi decoding", "Undoes the rate-½ convolutional code, correcting most bit errors from noise"),
        ("Frame sync", "Finds the fixed sync marker (1ACFFC1D) that starts every 1,024-byte frame"),
        ("Derandomise + Reed–Solomon", "Removes the scrambling pattern; Reed–Solomon fixes up to 16 bad bytes per block"),
        ("Packets", "Frames carry packets; each packet's ID (APID 64–69) says which camera channel it holds"),
        ("JPEG blocks", "Each packet holds a strip of 8×8-pixel blocks, compressed like a JPEG photo"),
        ("Image channels", "Blocks are reassembled into three ~1 km-resolution images, line by line"),
    ]
    fig, ax = plt.subplots(figsize=(11.5, 8.2))
    ax.set_xlim(0, 23); ax.set_ylim(0, len(layers) * 1.45 + 1.0); ax.axis("off")
    ax.text(0.2, len(layers) * 1.45 + 0.55, "How a Meteor-M LRPT signal becomes an image",
            fontsize=14, weight="bold", color=INK)
    for i, (name, desc) in enumerate(layers):
        y = (len(layers) - 1 - i) * 1.45 + 0.2
        kind = "accent" if i in (0, len(layers) - 1) else "plain"
        box(ax, 0.3, y, 6.4, 1.05, name, (), kind, 10)
        ax.text(7.1, y + 0.52, desc, fontsize=9, color=INK, va="center")
        if i < len(layers) - 1:
            arrow(ax, 3.5, y - 0.02, 3.5, y - 0.38)
    ax.text(0.3, -0.1, "Every layer exists to survive a weak, noisy signal from a satellite 1,000–3,000 km away.",
            fontsize=8.5, color=MUTED)
    fig.savefig(FIG_DIR / "prod_02_decode_stack.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


# ── 3. A real upcoming pass ───────────────────────────────────
def pass_curves(name, tle, start, place):
    orb = Orbital(name, line1=tle[0], line2=tle[1])
    _, lat, lon, alt = place
    passes = orb.get_next_passes(start, 48, lon, lat, alt, horizon=5)
    best = max(passes, key=lambda p: orb.get_observer_look(p[2], lon, lat, alt)[1])
    rise, fall, peak = best
    t = np.array([rise + timedelta(seconds=s) for s in range(0, int((fall - rise).total_seconds()) + 1, 5)])
    tt = t.astype("datetime64[ms]")
    _, el = orb.get_observer_look(tt, lon, lat, alt)
    pos, _ = orb.get_position(tt, normalize=False)
    opos, _ = observer_position(tt, lon, lat, alt)
    n = len(tt)
    P = np.vstack([np.broadcast_to(np.asarray(c, float), (n,)) for c in pos])
    O = np.vstack([np.broadcast_to(np.asarray(c, float), (n,)) for c in opos])
    rng = np.linalg.norm(P - O, axis=0)
    rate = np.gradient(rng, 5.0)
    doppler_khz = -137.9e6 * rate / C_LIGHT / 1e3
    return t, el, rng, doppler_khz, (rise, fall, peak)

def fig_pass(tles):
    start = datetime(2026, 11, 12, 0, 0)
    name = "METEOR-M2 3"
    t, el, rng, dop, (rise, fall, peak) = pass_curves(name, tles[name], start, PLACE)
    mins = np.array([(x - rise).total_seconds() / 60 for x in t])
    ist = lambda d: (d + timedelta(hours=5, minutes=30)).strftime("%H:%M")
    fig, axes = plt.subplots(3, 1, figsize=(9, 7.6), sharex=True)
    axes[0].plot(mins, el, color=NAVY)
    axes[0].axhspan(0, 20, color=PALE_ORANGE, zorder=0)
    axes[0].text(0.2, 12, "below ~20°: weak, noisy signal", fontsize=8, color=ORANGE)
    axes[0].set_ylabel("Elevation (°)")
    axes[1].plot(mins, rng, color=NAVY)
    axes[1].set_ylabel("Distance (km)")
    axes[2].plot(mins, dop, color=NAVY)
    axes[2].axhline(0, color=GREY, lw=1, ls="--")
    axes[2].set_ylabel("Doppler shift (kHz)")
    axes[2].set_xlabel(f"Minutes after the satellite rises ({ist(rise)} IST)")
    pk = np.argmax(el)
    for ax in axes:
        ax.axvline(mins[pk], color=ORANGE, lw=1, ls=":")
    axes[0].annotate(f"highest point {el[pk]:.0f}°\nat {ist(t[pk])} IST", (mins[pk], el[pk]),
                     xytext=(40, -10), textcoords="offset points", fontsize=8, color=INK)
    axes[1].annotate(f"closest {rng[pk]:.0f} km", (mins[pk], rng[pk]), xytext=(-110, 20),
                     textcoords="offset points", fontsize=8, color=INK)
    fig.suptitle(f"A real upcoming Meteor-M2 3 pass over Manali, {(rise + timedelta(hours=5.5)).strftime('%d %b %Y')}",
                 fontsize=12, weight="bold", color=INK, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "prod_03_pass.png", dpi=170)
    plt.close(fig)
    return {"rise_ist": ist(rise), "fall_ist": ist(fall), "peak_ist": ist(t[pk]),
            "duration_min": round((fall - rise).total_seconds() / 60, 1), "max_el": round(float(el[pk])),
            "min_range": round(float(rng[pk])), "max_range": round(float(rng.max())),
            "doppler_khz": round(float(np.abs(dop).max()), 1), "date": (rise + timedelta(hours=5.5)).strftime("%d %B %Y")}


def main():
    tles = read_tles(sys.argv[1])
    fig_system()
    fig_decode()
    info = fig_pass(tles)
    print(info)
    (FIG_DIR / "prod_pass.json").write_text(__import__("json").dumps(info))


if __name__ == "__main__":
    main()


# ── 1b. System overview with the real parts (from the product requirements) ──
def fig_system_hw():
    fig, ax = plt.subplots(figsize=(11, 7.4))
    ax.set_xlim(0, 22); ax.set_ylim(0, 14.8); ax.axis("off")
    ax.text(0.3, 14.35, "Inside SummitSathi: the parts and what each one does", fontsize=14, weight="bold", color=INK)
    box(ax, 0.6, 11.0, 5.6, 2.4, "Meteor-M satellite", ["~830 km up, polar orbit", "LRPT broadcast, 137 MHz"], "accent", 10.5)
    arrow(ax, 6.25, 12.2, 7.55, 12.2, color=ORANGE)
    box(ax, 7.6, 11.0, 4.0, 2.4, "Antenna", ["137 MHz V-dipole", "on a deployable", "rear mast"])
    arrow(ax, 11.65, 12.2, 12.55, 12.2)
    box(ax, 12.6, 11.0, 4.0, 2.4, "LNA", ["Low-noise amplifier", "on the antenna feed;", "boosts weak signal"])
    arrow(ax, 16.65, 12.2, 17.55, 12.2)
    box(ax, 17.6, 11.0, 4.0, 2.4, "RTL-SDR Blog V4", ["Software radio, USB;", "RF-shielded", "compartment"])
    ax.add_patch(plt.Rectangle((0.6, 3.3), 21.0, 6.9, facecolor="#FAFAFA", edgecolor=NAVY, linewidth=1.2))
    ax.text(0.9, 9.75, "RASPBERRY PI 5 (4 GB) — runs all software offline", fontsize=8.5, weight="bold", color=NAVY)
    arrow(ax, 19.6, 10.95, 19.6, 9.25)
    row1 = [(17.6, "Demodulate", ["Radio signal → bits"]), (12.6, "Decode", ["Error correction →", "data packets"]),
            (7.6, "Rebuild image", ["3 image channels,", "about 1 km per pixel"]), (2.6, "Physics", ["Pixels → cloud-top", "temperature"])]
    for i, (x, t, l) in enumerate(row1):
        box(ax, x, 7.0, 4.0, 2.2, t, l, "plain", 10)
        if i < len(row1) - 1:
            arrow(ax, x - 0.05, 8.1, row1[i + 1][0] + 4.05, 8.1)
    row2 = [(2.6, "Map", ["Orbit → position", "of every pixel"]), (8.0, "Measure", ["46 cloud measurements", "around the trekker"]),
            (13.4, "Predict + score", ["Climb Risk 0–100,", "advice, safety rules"])]
    arrow(ax, 4.6, 6.95, 4.6, 6.25)
    for i, (x, t, l) in enumerate(row2):
        box(ax, x, 4.0, 4.0, 2.2, t, l, "accent" if i == 2 else "plain", 10)
        if i < len(row2) - 1:
            arrow(ax, x + 4.05, 5.1, row2[i + 1][0] - 0.05, 5.1)
    box(ax, 2.3, 0.3, 4.6, 2.3, "Storage", ["128 GB microSD: maps,", "models, orbit data"], "input", 10)
    arrow(ax, 4.6, 2.65, 4.6, 3.95, color=GREY, ls="--")
    box(ax, 7.7, 0.3, 4.6, 2.3, "GPS + clock", ["u-blox NEO-M9N GPS;", "DS3231 real-time clock"], "input", 10)
    arrow(ax, 10.0, 2.65, 10.0, 3.95, color=GREY, ls="--")
    box(ax, 13.1, 0.3, 4.6, 2.3, "7-inch screen", ["800-nit touchscreen,", "works with gloves"], "accent", 10)
    arrow(ax, 15.4, 3.95, 15.4, 2.65, color=ORANGE)
    box(ax, 18.3, 0.3, 3.3, 2.3, "Battery", ["4 × 18650 cells,", "≥12 h target"], "input", 10)
    fig.savefig(FIG_DIR / "prod_01b_system_hw.png", dpi=170)
    plt.close(fig)
