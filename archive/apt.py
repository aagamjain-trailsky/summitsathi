"""
Real NOAA APT image processing.

A decoded APT line is 2080 words (4160 words/s, 2 lines/s):

    0     39    86          995   1040  1079  1126         2035  2080
    |syncA|spcA | image A    |telA |syncB|spcB | image B    |telB |

Telemetry repeats every 128 lines as 16 wedges of 8 lines:
    1-8   grey scale (1/8 ... 8/8 of full scale) — used for calibration
    9     zero modulation reference
    10-13 black-body thermistor (PRT) counts
    14    patch temperature
    15    back-scan (internal black-body view) for this channel
    16    channel ID (equals the value of wedge 1..6)
"""
import numpy as np
from PIL import Image
from scipy.ndimage import median_filter

LINE_WORDS = 2080
SYNC_A   = slice(0, 39)
SPACE_A  = slice(39, 86)
IMAGE_A  = slice(86, 995)
TELEM_A  = slice(995, 1040)
SPACE_B  = slice(1079, 1126)
IMAGE_B  = slice(1126, 2035)
TELEM_B  = slice(2035, 2080)

FRAME_LINES = 128
WEDGE_LINES = 8
WEDGE_LEVELS = np.arange(1, 9) * (255 / 8)  # ideal wedges 1-8

# Wedge-16 value (in units of wedges 1..6) → AVHRR channel
CHANNEL_ID = {1: "1", 2: "2", 3: "3A", 4: "4", 5: "5", 6: "3B"}
IR_CHANNELS = {"3B", "4", "5"}

# Sync A: 7 cycles of 1040 Hz square wave (4 words per cycle)
_SYNC = np.array([0] * 4 + [1, 1, 0, 0] * 7 + [0] * 7, dtype=np.float32)
_SYNC = (_SYNC - _SYNC.mean()) / np.linalg.norm(_SYNC - _SYNC.mean())

# Central wavenumbers (cm⁻¹) — close for NOAA-15/18/19
NU_CH4 = 925.0
NU_CH3B = 2670.0
C1 = 1.191042e-5   # mW/(m² sr cm⁻⁴)
C2 = 1.4387752     # K cm
NOMINAL_BB_K = 290.0


def planck(nu, t):
    return C1 * nu ** 3 / (np.exp(C2 * nu / t) - 1)

def inv_planck(nu, r):
    r = np.clip(r, 1e-6, None)
    return C2 * nu / np.log(1 + C1 * nu ** 3 / r)


# ── Line alignment ─────────────────────────────────────────────
def align_lines(img: np.ndarray):
    """Find sync A in every line; return aligned image and per-line sync score."""
    x = img.astype(np.float32)
    x = x - x.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(x, axis=1) + 1e-6

    # Circular cross-correlation of every row with the sync pattern
    kernel = np.zeros(LINE_WORDS, dtype=np.float32)
    kernel[:len(_SYNC)] = _SYNC
    corr = np.fft.irfft(np.fft.rfft(x, axis=1) * np.conj(np.fft.rfft(kernel)), n=LINE_WORDS, axis=1)
    offset = corr.argmax(axis=1)
    # Normalise by local energy of the 39-word window so score is in [−1, 1]
    peak = corr[np.arange(len(x)), offset]
    win = np.array([np.linalg.norm(np.roll(x[i], -offset[i])[:39]) for i in range(len(x))]) + 1e-6
    score = peak / win
    score[norms < 1.0] = 0.0

    # Use a running median of offsets so noisy lines don't jump around
    good = score > 0.6
    if good.sum() < 10:
        return img, score, np.zeros(len(img), dtype=int)
    smooth = offset.copy()
    idx = np.where(good)[0]
    smooth = np.interp(np.arange(len(img)), idx, offset[idx]).round().astype(int)

    aligned = np.stack([np.roll(img[i], -smooth[i]) for i in range(len(img))])
    return aligned, score, smooth


# ── Telemetry frame and calibration ────────────────────────────
def _telemetry_series(img, telem):
    cols = img[:, telem].astype(np.float32)
    return np.median(cols[:, 8:-8], axis=1)

def find_frame_phase(tel: np.ndarray, valid: np.ndarray) -> tuple:
    """Find which line starts wedge 1 by matching the 1..8 ramp + zero wedge."""
    ideal = np.concatenate([np.repeat(WEDGE_LEVELS, WEDGE_LINES), np.zeros(WEDGE_LINES)])
    best, best_score = 0, -np.inf
    for p in range(FRAME_LINES):
        scores = []
        for start in range(p, len(tel) - len(ideal), FRAME_LINES):
            seg, ok = tel[start:start + len(ideal)], valid[start:start + len(ideal)]
            if ok.mean() < 0.6:
                continue
            scores.append(np.corrcoef(seg[ok], ideal[ok])[0, 1])
        if scores and np.median(scores) > best_score:
            best, best_score = p, float(np.median(scores))
    return best, best_score

def frame_wedges(tel, start, ok=None):
    """Median value of each of the 16 wedges in the frame starting at `start`.
    Clean lines are preferred; a wedge with fewer than 2 clean lines uses
    all of its lines (the monotonicity check still rejects bad frames)."""
    w = []
    for k in range(16):
        lo, hi = start + k * WEDGE_LINES + 2, start + (k + 1) * WEDGE_LINES - 2
        seg = tel[lo:hi]
        if ok is not None and ok[lo:hi].sum() >= 2:
            seg = seg[ok[lo:hi]]
        w.append(np.median(seg) if len(seg) else np.nan)
    return np.array(w)

def calibration_curve(wedges):
    """Monotone mapping measured counts → ideal levels from wedges 9 (zero) and 1-8."""
    measured = np.concatenate([[wedges[8]], wedges[:8]])
    ideal = np.concatenate([[0.0], WEDGE_LEVELS])
    if np.any(np.isnan(measured)) or np.any(np.diff(measured) <= 0):
        return None
    return measured, ideal


def _two_point_bt(counts, space_strip, wedges, curve, nu, min_gap=60):
    """Counts → brightness temperature. Cold is bright in APT IR, so deep
    space has the highest count and the warm black body (wedge 15) a low one."""
    if len(space_strip) == 0:
        return np.nan
    space = np.interp(np.median(space_strip), *curve)
    backscan = np.interp(wedges[14], *curve)
    if space - backscan <= min_gap:
        return np.nan
    r = planck(nu, NOMINAL_BB_K) * (space - counts) / (space - backscan)
    return inv_planck(nu, r)

def _channel(wedges, curve) -> str:
    """Wedge 16 equals one of wedges 1-6; reject if it isn't close to any."""
    v = np.interp(wedges[15], *curve) / (255 / 8)
    k = int(round(v))
    return CHANNEL_ID.get(k, "?") if abs(v - k) < 0.3 else "?"


# ── Main entry ─────────────────────────────────────────────────
def process(path: str) -> dict:
    img = np.array(Image.open(path).convert("L"))
    if img.shape[1] != LINE_WORDS:
        raise ValueError(f"Not an APT image (width {img.shape[1]})")

    # SatNOGS images are padded with black rows after the pass ends
    live = img.max(axis=1) > 0
    n_lines = int(np.where(live)[0].max() + 1) if live.any() else 0
    img = img[:n_lines]
    if n_lines < FRAME_LINES * 2:
        raise ValueError(f"Too short ({n_lines} lines)")

    aligned, sync_score, _ = align_lines(img)

    # The space-view strips are flat on a clean line, so their spread is
    # a per-line noise measure. IQR ignores sparse speckle interference,
    # which the median filter below removes instead.
    def _iqr(cols):
        q = np.percentile(aligned[:, cols][:, 4:-4].astype(np.float32), [25, 75], axis=1)
        return q[1] - q[0]
    space_noise = np.maximum(_iqr(SPACE_A), _iqr(SPACE_B))
    line_ok = (sync_score > 0.5) & (space_noise < 10)

    # Speckle interference removed from the image areas before calibration
    clean = aligned.copy()
    clean[:, IMAGE_A] = median_filter(aligned[:, IMAGE_A], size=3)
    clean[:, IMAGE_B] = median_filter(aligned[:, IMAGE_B], size=3)

    tel_a = _telemetry_series(aligned, TELEM_A)
    tel_b = _telemetry_series(aligned, TELEM_B)
    phase, phase_score = find_frame_phase(tel_b, line_ok)

    a = np.full(aligned[:, IMAGE_A].shape, np.nan, dtype=np.float32)
    b = np.full(aligned[:, IMAGE_B].shape, np.nan, dtype=np.float32)
    bt_b = np.full(b.shape, np.nan, dtype=np.float32)
    bt_a = np.full(a.shape, np.nan, dtype=np.float32)
    ch_a = np.array([""] * n_lines, dtype=object)
    ch_b = np.array([""] * n_lines, dtype=object)

    # Keep only frames whose grey-scale wedges are clean and monotone
    frames, all_wa, all_wb = [], [], []
    for s in range(phase, n_lines - FRAME_LINES + 1, FRAME_LINES):
        if line_ok[s:s + FRAME_LINES].mean() < 0.5:
            continue
        wa, wb = frame_wedges(tel_a, s, line_ok), frame_wedges(tel_b, s, line_ok)
        all_wa.append(wa)
        all_wb.append(wb)
        ca, cb = calibration_curve(wa), calibration_curve(wb)
        if ca is None or cb is None:
            continue
        frames.append({"start": s, "span": (s, s + FRAME_LINES), "wa": wa, "wb": wb,
                       "ca": ca, "cb": cb, "id_a": _channel(wa, ca), "id_b": _channel(wb, cb)})

    # Fallback: no single frame is clean enough, but the wedges are stable
    # through a pass, so combine every partial frame into one calibration.
    if not frames and all_wa:
        wa, wb = np.nanmedian(np.array(all_wa), axis=0), np.nanmedian(np.array(all_wb), axis=0)
        ca, cb = calibration_curve(wa), calibration_curve(wb)
        if ca is not None and cb is not None:
            frames.append({"start": 0, "span": (0, n_lines), "wa": wa, "wb": wb,
                           "ca": ca, "cb": cb, "id_a": _channel(wa, ca), "id_b": _channel(wb, cb)})

    # Channel ID: an unreadable frame takes its neighbour's value
    for key in ("id_a", "id_b"):
        ids = [f[key] for f in frames]
        for i, v in enumerate(ids):
            if v == "?":
                near = [ids[j] for j in (i - 1, i + 1) if 0 <= j < len(ids) and ids[j] != "?"]
                frames[i][key] = near[0] if near else "?"

    for i, f in enumerate(frames):
        lo = 0 if i == 0 else f["start"]
        hi = n_lines if i == len(frames) - 1 else frames[i + 1]["start"]
        rows = slice(lo, hi)

        a[rows] = np.interp(clean[rows, IMAGE_A], *f["ca"])
        b[rows] = np.interp(clean[rows, IMAGE_B], *f["cb"])
        ch_a[rows] = f["id_a"]
        ch_b[rows] = f["id_b"]

        # Approximate brightness temperatures: two-point calibration
        # between deep space and the internal black body (black body
        # assumed at a nominal temperature — see README).
        lo, hi = f["span"]
        frame = aligned[lo:hi][line_ok[lo:hi]]
        if f["id_b"] == "4":
            bt_b[rows] = _two_point_bt(b[rows], frame[:, SPACE_B], f["wb"], f["cb"], NU_CH4)
        # Channel A at night is 3B (3.7 µm); the ID wedge often reads as 3A,
        # so calibrate it whenever it is a channel-3 band. process.py only
        # uses it where the scene is dark (3A cannot be observed at night).
        if f["id_a"] in ("3A", "3B"):
            bt_a[rows] = _two_point_bt(a[rows], frame[:, SPACE_A], f["wa"], f["ca"], NU_CH3B, min_gap=25)

    calibrated = len(frames)
    bt_b[(bt_b < 170) | (bt_b > 340)] = np.nan
    bt_a[(bt_a < 200) | (bt_a > 340)] = np.nan

    a[~line_ok] = np.nan
    b[~line_ok] = np.nan
    bt_b[~line_ok] = np.nan
    bt_a[~line_ok] = np.nan

    return {
        "n_lines":      n_lines,
        "good_lines":   int(line_ok.sum()),
        "sync_quality": float(np.median(sync_score)),
        "frame_phase":  int(phase),
        "phase_score":  float(phase_score),
        "frames_calibrated": calibrated,
        "image_a":      a,
        "image_b":      b,
        "bt_b":         bt_b,
        "bt_a":         bt_a,
        "channel_a":    ch_a,
        "channel_b":    ch_b,
        "line_ok":      line_ok,
    }
