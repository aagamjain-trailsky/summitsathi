"""
Score the alert logic against what the weather actually did.

  v1  — the original SummitSathi thresholds, unchanged
  v2  — thresholds / logistic model fitted on cloud-top temperature,
        trained on passes before SPLIT_DATE, tested on passes after it
  climatology — rate of the event for that location and month (baseline)

    python -m archive.evaluate
"""
import csv
import json
import math
import numpy as np
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import connect, ARCHIVE_DIR
from archive import truth

RESULTS_DIR = ARCHIVE_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
SPLIT_DATE = "2024-01-01"
RNG = np.random.default_rng(42)

FEATURES = ["bt_min", "bt_p10", "bt_p50", "bt_std", "frac_lt_273", "frac_lt_253",
            "frac_lt_233", "frac_lt_220", "storm_dist_km", "cold_px_50km", "cold_px_150km",
            "btd_p50", "frac_btd_gt2", "has_3b", "abs_scan", "is_day",
            "hour_sin", "hour_cos", "month_sin", "month_cos"]

# Local history (airport × month × time of day, METAR before the split)
CLIM_FEATURES = ["clim_rain", "clim_thunder", "clim_fog", "clim_cloudy"]

# v2 single-threshold rule per event: (feature, sign). sign −1 means
# "alert when the feature is BELOW the threshold" (e.g. colder cloud tops).
THRESHOLD_RULE = {
    "rain_now":    ("bt_min", -1),
    "thunder_now": ("bt_min", -1),
    "rain_next3h": ("bt_min", -1),
    "fog_now":     ("btd_p50", 1),      # night only; no 3B channel → no fog alert
    "cloudy_now":  ("frac_lt_253", 1),
}
MODEL_PATH = RESULTS_DIR / "model_v2.json"

# Event → (label function, v1 prediction function)
def _v1_rain(v1):    return v1["rain_rate"] in ("moderate", "heavy")
def _v1_thunder(v1): return v1["lightning_risk"] == "high"
def _v1_fog(v1):     return v1["fog_pct"] > 2.0
def _v1_cloudy(v1):  return v1["cloud_cover_pct"] >= 75

EVENTS = {
    "rain_now":     (lambda m, e: m["rain"] if m else None,                 _v1_rain),
    "thunder_now":  (lambda m, e: m["thunder"] if m else None,              _v1_thunder),
    "rain_next3h":  (lambda m, e: m["rain_next3h"] if m else None,          _v1_rain),
    "fog_now":      (lambda m, e: m["fog"] if m else None,                  _v1_fog),
    "cloudy_now":   (lambda m, e: e["cloud_cover"] >= 75 if e and e["cloud_cover"] is not None else None, _v1_cloudy),
}


# ── Build the joined dataset ───────────────────────────────────
def build_dataset() -> list:
    conn = connect()
    rows = conn.execute("""SELECT s.*, o.satellite, o.max_elev_deg FROM samples s
                           JOIN observations o ON o.obs_id = s.obs_id""").fetchall()
    data = []
    for r in rows:
        f = json.loads(r["features"])
        if "bt_p50" not in f or "v1" not in f:
            continue
        t = datetime.strptime(r["time_utc"], "%Y-%m-%dT%H:%M:%S")
        e = truth.era5_at(r["location"], t, hours_ahead=3)
        m_now = truth.metar_window(r["location"], t, 1, 1)
        m_next = truth.metar_window(r["location"], t, 0, 3)
        m = None
        if m_now:
            m = dict(m_now)
            m["rain_next3h"] = bool(m_next and m_next["rain"])
        f["abs_scan"] = abs(f["scan_angle"])
        f["is_day"] = float(f["sun_zenith"] < 85)
        f["has_3b"] = float("btd_p50" in f)
        f["hour_sin"] = math.sin(2 * math.pi * f.get("local_hour", 0) / 24)
        f["hour_cos"] = math.cos(2 * math.pi * f.get("local_hour", 0) / 24)
        f["month_sin"] = math.sin(2 * math.pi * t.month / 12)
        f["month_cos"] = math.cos(2 * math.pi * t.month / 12)
        d = {"obs_id": r["obs_id"], "location": r["location"], "time": t,
             "satellite": r["satellite"], "features": f, "era5": e, "metar": m}
        for ev, (label, _) in EVENTS.items():
            d[ev] = label(m, e)
        data.append(d)
    return data


# ── Metrics ────────────────────────────────────────────────────
def confusion(y, p) -> dict:
    y, p = np.asarray(y, bool), np.asarray(p, bool)
    tp, fp = int((y & p).sum()), int((~y & p).sum())
    fn, tn = int((y & ~p).sum()), int((~y & ~p).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    far = fp / (tp + fp) if tp + fp else 0.0
    return {"n": len(y), "events": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec, "recall": rec, "f1": f1, "false_alarm_ratio": far,
            "accuracy": (tp + tn) / len(y) if len(y) else 0.0}

def auc(y, score) -> float:
    y, s = np.asarray(y, bool), np.asarray(score, float)
    if y.all() or (~y).all():
        return float("nan")
    ranks = np.argsort(np.argsort(s)) + 1
    n1, n0 = y.sum(), (~y).sum()
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def bootstrap_f1(y, p, n=1000) -> tuple:
    y, p = np.asarray(y, bool), np.asarray(p, bool)
    vals = []
    for _ in range(n):
        k = RNG.integers(0, len(y), len(y))
        vals.append(confusion(y[k], p[k])["f1"])
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


# ── Models ─────────────────────────────────────────────────────
def matrix(rows, features=FEATURES) -> np.ndarray:
    return np.array([[r["features"].get(k, np.nan) for k in features] for r in rows], float)

class Logistic:
    """Plain L2-regularised logistic regression (gradient descent)."""
    def fit(self, X, y, lr=0.1, steps=3000, l2=1e-2):
        self.mu = np.nanmean(X, axis=0)
        self.sd = np.nanstd(X, axis=0) + 1e-9
        Z = self._z(X)
        y = np.asarray(y, float)
        w = np.zeros(Z.shape[1]); b = math.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6))
        for _ in range(steps):
            p = 1 / (1 + np.exp(-(Z @ w + b)))
            w -= lr * (Z.T @ (p - y) / len(y) + l2 * w)
            b -= lr * (p - y).mean()
        self.w, self.b = w, b
        return self
    def _z(self, X):
        Z = (X - self.mu) / self.sd
        return np.nan_to_num(Z)
    def predict_proba(self, X):
        return 1 / (1 + np.exp(-(self._z(X) @ self.w + self.b)))

def best_threshold(y, score) -> float:
    """Threshold on score that maximises F1 (fit on training data only)."""
    y = np.asarray(y, bool)
    best, best_f1 = None, -1
    for t in np.unique(np.percentile(score, np.linspace(1, 99, 99))):
        f1 = confusion(y, score >= t)["f1"]
        if f1 > best_f1:
            best, best_f1 = float(t), f1
    return best

# Event → METAR flag used for the climatology baseline
CLIM_FLAG = {"rain_now": "rain", "thunder_now": "thunder", "rain_next3h": "rain",
             "fog_now": "fog", "cloudy_now": None}
_clim_cache = {}

def _metar_climatology(loc_id: str, split: datetime, exclude_years=()) -> dict:
    """Event frequency per (month, 3-hour local block) from every METAR
    report at this airport before the split date, skipping excluded years."""
    key = (loc_id, split, tuple(sorted(exclude_years)))
    if key in _clim_cache:
        return _clim_cache[key]
    counts = {}
    lon = truth.locations()[loc_id]["lon"]
    for year in range(2018, split.year + 1):
        if year in exclude_years:
            continue
        for t, m in (truth._metar(loc_id, year) or []):
            if t >= split:
                continue
            block = int(((t.hour + lon / 15) % 24) // 3)
            c = counts.setdefault((t.month, block), {"n": 0, "rain": 0, "thunder": 0,
                                                     "fog": 0, "cloudy": 0})
            c["n"] += 1
            c["rain"] += m["rain"]
            c["thunder"] += m["thunder"]
            c["fog"] += m["fog"]
            c["cloudy"] += m["oktas"] >= 6
    _clim_cache[key] = counts
    return counts

def climatology(rows, event, split, exclude_years=()) -> np.ndarray:
    """Baseline: how often this event is reported at this airport, in this
    month, at this time of day — from the full METAR history before the split."""
    flag = CLIM_FLAG[event] or "cloudy"
    out = []
    for r in rows:
        counts = _metar_climatology(r["location"], split, exclude_years)
        block = int(r["features"].get("local_hour", 12) // 3)
        c = counts.get((r["time"].month, block))
        out.append(c[flag] / c["n"] if c and c["n"] >= 20 else np.nan)
    out = np.array(out, float)
    return np.where(np.isnan(out), np.nanmean(out) if np.isfinite(out).any() else 0.0, out)


# ── Main ───────────────────────────────────────────────────────
def evaluate():
    data = build_dataset()
    print(f"[EVAL] {len(data)} location samples with features")
    split = datetime.strptime(SPLIT_DATE, "%Y-%m-%d")
    for ev_flag, feat in (("rain_now", "clim_rain"), ("thunder_now", "clim_thunder"),
                          ("fog_now", "clim_fog"), ("cloudy_now", "clim_cloudy")):
        for r, v in zip(data, climatology(data, ev_flag, split)):
            r["features"][feat] = float(v)
    report = {"n_samples": len(data), "split_date": SPLIT_DATE, "events": {}}
    models = {}

    for ev, (_, v1_fn) in EVENTS.items():
        rows = [r for r in data if r[ev] is not None]
        train = [r for r in rows if r["time"] < split]
        test = [r for r in rows if r["time"] >= split]
        if len(train) < 50 or len(test) < 30 or sum(r[ev] for r in train) < 5:
            report["events"][ev] = {"skipped": f"too few samples (train {len(train)}, test {len(test)})"}
            continue

        y_tr = np.array([r[ev] for r in train], bool)
        y_te = np.array([r[ev] for r in test], bool)

        # v1 — original thresholds
        v1_te = np.array([v1_fn(r["features"]["v1"]) for r in test])

        # v2a — single tuned threshold on the most physical feature
        key, sign = THRESHOLD_RULE[ev]
        rule_score = lambda rows: np.array([sign * r["features"].get(key, np.nan) for r in rows])
        s_tr = np.nan_to_num(rule_score(train), nan=-1e9)
        s_te = np.nan_to_num(rule_score(test), nan=-1e9)
        t = best_threshold(y_tr, s_tr)
        v2a_te = s_te >= t

        # v2b — logistic regression on all features
        model = Logistic().fit(matrix(train), y_tr)
        p_tr, p_te = model.predict_proba(matrix(train)), model.predict_proba(matrix(test))
        tp = best_threshold(y_tr, p_tr)
        v2b_te = p_te >= tp

        models[ev] = {
            "threshold": {"feature": key, "sign": sign, "threshold": sign * t},
            "logistic": {"features": FEATURES, "mu": list(map(float, model.mu)),
                         "sd": list(map(float, model.sd)), "w": list(map(float, model.w)),
                         "b": float(model.b), "prob_threshold": float(tp)},
            "trained_on": f"passes before {SPLIT_DATE}", "n_train": len(train),
        }

        # v2c — satellite + local history: does the satellite add information
        # beyond what the airport's own climate record already says?
        comb = FEATURES + CLIM_FEATURES
        model_c = Logistic().fit(matrix(train, comb), y_tr)
        pc_tr, pc_te = model_c.predict_proba(matrix(train, comb)), model_c.predict_proba(matrix(test, comb))
        v2c_te = pc_te >= best_threshold(y_tr, pc_tr)

        clim = climatology(test, ev, split)
        tc = best_threshold(y_tr, climatology(train, ev, split))

        report["events"][ev] = {
            "train": {"n": len(train), "events": int(y_tr.sum())},
            "test":  {"n": len(test), "events": int(y_te.sum()), "base_rate": float(y_te.mean())},
            "v1":            {**confusion(y_te, v1_te), "f1_ci95": bootstrap_f1(y_te, v1_te)},
            "v2_threshold":  {**confusion(y_te, v2a_te), "f1_ci95": bootstrap_f1(y_te, v2a_te),
                              "feature": key, "sign": sign, "threshold": sign * t,
                              "auc": auc(y_te, s_te)},
            "v2_logistic":   {**confusion(y_te, v2b_te), "f1_ci95": bootstrap_f1(y_te, v2b_te),
                              "auc": auc(y_te, p_te),
                              "weights": dict(zip(FEATURES, map(float, model.w)))},
            "v2_combined":   {**confusion(y_te, v2c_te), "f1_ci95": bootstrap_f1(y_te, v2c_te),
                              "auc": auc(y_te, pc_te),
                              "auc_gain_over_climatology": auc(y_te, pc_te) - auc(y_te, clim)},
            "climatology":   {**confusion(y_te, clim >= tc), "auc": auc(y_te, clim)},
        }

    (RESULTS_DIR / "metrics.json").write_text(json.dumps(report, indent=1, default=str))
    MODEL_PATH.write_text(json.dumps(models, indent=1))
    export_csv(data)
    print_summary(report)
    return report

def export_csv(data):
    keys = sorted({k for r in data for k in r["features"] if k != "v1"})
    with open(RESULTS_DIR / "samples.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["obs_id", "location", "time_utc", "satellite"] + keys +
                   ["v1_cloud_cover_pct", "v1_rain_rate", "v1_lightning_risk"] +
                   list(EVENTS) + ["era5_cloud_cover", "era5_precip", "era5_precip_next3h", "era5_gust"])
        for r in data:
            f_, e, v1 = r["features"], r["era5"] or {}, r["features"]["v1"]
            w.writerow([r["obs_id"], r["location"], r["time"].isoformat(), r["satellite"]] +
                       [f_.get(k) for k in keys] +
                       [v1["cloud_cover_pct"], v1["rain_rate"], v1["lightning_risk"]] +
                       [r[ev] for ev in EVENTS] +
                       [e.get("cloud_cover"), e.get("precipitation"),
                        e.get("precip_next3h"), e.get("wind_gusts_10m")])

def print_summary(report):
    print(f"\n[EVAL] ── Results on held-out passes (from {report['split_date']}) ──")
    for ev, r in report["events"].items():
        if "skipped" in r:
            print(f"[EVAL] {ev}: {r['skipped']}")
            continue
        print(f"[EVAL] {ev}: test n={r['test']['n']}, events={r['test']['events']} "
              f"({r['test']['base_rate']:.0%})")
        for m in ("v1", "v2_threshold", "v2_logistic", "v2_combined", "climatology"):
            x = r[m]
            ci = x.get("f1_ci95")
            ci_s = f" [{ci[0]:.2f}–{ci[1]:.2f}]" if ci else ""
            auc_s = f"  AUC {x['auc']:.2f}" if "auc" in x else ""
            print(f"[EVAL]   {m:13s} F1 {x['f1']:.2f}{ci_s}  precision {x['precision']:.2f}  "
                  f"recall {x['recall']:.2f}{auc_s}")


if __name__ == "__main__":
    evaluate()
