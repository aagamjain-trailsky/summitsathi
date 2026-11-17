"""
v3 Climb Risk Score (0–100).

The score is the calibrated probability (×100) that a hazard is reported at
the location: a thunderstorm now, rain within 3 hours, or fog. A score of
30 should mean a hazard followed about 30 % of the time — this is checked on
years the model never saw.

  model        gradient-boosted trees on the v3 features
  calibration  isotonic regression fitted on the tuning year (2020)
  testing      leave-one-year-out, as in evaluate_v3.py
  bands        fixed in advance; the real hazard rate in each is measured
  safety rules floors justified on the tuning year, verified on test years

    python -m archive.risk_v3
"""
import json
import pickle
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.evaluate import build_dataset, auc, RESULTS_DIR
from archive.evaluate_v3 import (add_cooling_features, set_climatology, matrix, _hgb, GRID,
                                 V3_FEATURES, TUNE_YEARS, TEST_GROUPS)
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss

HAZARD_EVENTS = ("thunder_now", "rain_next3h", "fog_now")

# Bands are fixed before looking at any test result
BANDS = [(0, 10, "MINIMAL"), (10, 25, "LOW"), (25, 45, "MODERATE"),
         (45, 70, "HIGH"), (70, 101, "EXTREME")]
DECISION = {
    "MINIMAL":  "Conditions favourable — keep checking each pass",
    "LOW":      "Low risk — monitor conditions",
    "MODERATE": "Proceed with caution — set a turn-around time",
    "HIGH":     "High risk — avoid exposed ridges; consider turning back",
    "EXTREME":  "Do not climb — hazardous weather likely",
}

# Safety rules: (name, condition on features). Floors are set from the
# tuning year's observed hazard rate when the condition holds.
SAFETY_RULES = [
    ("storm_within_20km", lambda f: f.get("storm_dist_km", 999) < 20),
    ("overshooting_top_within_50km", lambda f: f.get("ot_count_50km", 0) > 0),
]
STALE_HOURS = 3.0


def band(score: float) -> str:
    for lo, hi, name in BANDS:
        if lo <= score < hi:
            return name
    return "EXTREME"

def hazard(r):
    vals = [r[e] for e in HAZARD_EVENTS]
    return None if any(v is None for v in vals) else bool(any(vals))

def climatology_any(f):
    """Baseline probability from the airport's own history."""
    p = [f.get(k, 0.0) for k in ("clim_thunder", "clim_rain", "clim_fog")]
    return 1 - np.prod([1 - x for x in p])


def fit_calibrated(train_inner, tune):
    """Choose settings on the tuning year, then calibrate on it."""
    y_in = np.array([r["hazard"] for r in train_inner], bool)
    y_tu = np.array([r["hazard"] for r in tune], bool)
    X_in, X_tu = matrix(train_inner, V3_FEATURES), matrix(tune, V3_FEATURES)
    best, best_ap = None, -1
    for cfg in GRID:
        p = _hgb(cfg).fit(X_in, y_in).predict_proba(X_tu)[:, 1]
        ap = average_precision_score(y_tu, p)
        if ap > best_ap:
            best, best_ap = cfg, ap
    model = _hgb(best).fit(X_in, y_in)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(model.predict_proba(X_tu)[:, 1], y_tu)
    floors = {}
    for name, cond in SAFETY_RULES:
        hit = [r["hazard"] for r in tune if cond(r["features"])]
        if len(hit) >= 10:
            floors[name] = {"floor_score": round(100 * float(np.mean(hit))), "tune_n": len(hit)}
    return model, iso, best, floors

def score_rows(rows, model, iso, floors):
    raw = model.predict_proba(matrix(rows, V3_FEATURES))[:, 1]
    cal = 100 * iso.predict(raw)
    out = []
    for r, s in zip(rows, cal):
        applied = []
        for name, cond in SAFETY_RULES:
            if name in floors and cond(r["features"]) and s < floors[name]["floor_score"]:
                s = floors[name]["floor_score"]
                applied.append(name)
        out.append((float(s), applied))
    return out


def reliability(scores, y, bins=10):
    edges = np.linspace(0, 100, bins + 1)
    table = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (scores >= lo) & (scores < hi if hi < 100 else scores <= hi)
        if m.sum():
            table.append({"bin": f"{lo:.0f}–{hi:.0f}", "n": int(m.sum()),
                          "mean_score": float(scores[m].mean()),
                          "observed_rate_pct": float(100 * y[m].mean())})
    return table


def run():
    data = build_dataset()
    add_cooling_features(data)
    for r in data:
        r["hazard"] = hazard(r)
    rows = [r for r in data if r["hazard"] is not None]
    tune = [r for r in rows if r["time"].year in TUNE_YEARS]
    print(f"[RISK] {len(rows)} samples with ground truth; hazard rate {np.mean([r['hazard'] for r in rows]):.1%}")

    y_all, s_all, s_raw, base_all, groups, overrides, meta = [], [], [], [], [], [], []
    fold_info = []
    for g in TEST_GROUPS:
        test = [r for r in rows if r["time"].year in g]
        inner = [r for r in rows if r["time"].year not in g and r["time"].year not in TUNE_YEARS]
        if not test or not inner:
            continue
        set_climatology(rows, g)                     # history never includes test years
        model, iso, cfg, floors = fit_calibrated(inner, tune)
        scored = score_rows(test, model, iso, floors)
        raw = 100 * iso.predict(model.predict_proba(matrix(test, V3_FEATURES))[:, 1])
        y = [r["hazard"] for r in test]
        y_all += y
        s_all += [s for s, _ in scored]
        s_raw += list(raw)
        overrides += [a for _, a in scored]
        base_all += [100 * climatology_any(r["features"]) for r in test]
        groups += ["-".join(map(str, sorted(g)))] * len(test)
        meta += [{"location": r["location"], "time": r["time"].isoformat(), "obs_id": r["obs_id"]}
                 for r in test]
        fold_info.append({"test_years": sorted(g), "n": len(test), "settings": cfg, "floors": floors,
                          "auc": auc(y, [s for s, _ in scored])})

    y, s = np.array(y_all, bool), np.array(s_all)
    base = np.array(base_all)
    brier = brier_score_loss(y, s / 100)
    brier_clim = brier_score_loss(y, base / 100)

    bands = []
    for lo, hi, name in BANDS:
        m = (s >= lo) & (s < hi)
        bands.append({"band": name, "score_range": f"{lo}–{min(hi, 100)}", "n": int(m.sum()),
                      "share_of_cases_pct": float(100 * m.mean()),
                      "observed_hazard_rate_pct": float(100 * y[m].mean()) if m.sum() else None,
                      "decision": DECISION[name]})

    rule_checks = {}
    feats = [r for g in TEST_GROUPS for r in rows if r["time"].year in g]
    for name, cond in SAFETY_RULES:
        hit = np.array([r["hazard"] for r in feats if cond(r["features"])], bool)
        rule_checks[name] = {"test_n": int(len(hit)),
                             "test_hazard_rate_pct": float(100 * hit.mean()) if len(hit) else None,
                             "times_applied": int(sum(name in a for a in overrides))}

    report = {
        "definition": "Calibrated probability (×100) of a thunderstorm now, rain within 3 h, or fog, "
                      "reported at the location",
        "test_n": int(len(y)), "hazard_rate_pct": float(100 * y.mean()),
        "auc": auc(y, s), "auc_without_safety_rules": auc(y, np.array(s_raw)),
        "brier": float(brier), "brier_climatology": float(brier_clim),
        "brier_skill_vs_climatology": float(1 - brier / brier_clim),
        "reliability": reliability(s, y), "bands": bands,
        "safety_rules": rule_checks, "folds": fold_info,
        "stale_after_hours": STALE_HOURS,
    }
    (RESULTS_DIR / "risk_v3.json").write_text(json.dumps(report, indent=1, default=str))
    (RESULTS_DIR / "risk_predictions_v3.json").write_text(json.dumps(
        {"y": y.astype(int).tolist(), "score": s.tolist(), "baseline": base.tolist(),
         "group": groups, "meta": meta}))

    # Deployable model: trained on every year except the tuning year,
    # calibrated and safety floors set on the tuning year.
    set_climatology(rows, ())
    inner = [r for r in rows if r["time"].year not in TUNE_YEARS]
    model, iso, cfg, floors = fit_calibrated(inner, tune)
    with open(RESULTS_DIR / "model_risk_v3.pkl", "wb") as f:
        pickle.dump({"model": model, "calibration": iso, "features": V3_FEATURES, "settings": cfg,
                     "floors": floors, "bands": BANDS, "decision": DECISION,
                     "stale_after_hours": STALE_HOURS}, f)

    print(f"\n[RISK] ── Climb Risk Score, out-of-year test (n={len(y):,}) ──")
    print(f"[RISK] AUC {report['auc']:.2f}   Brier {brier:.3f} vs local history {brier_clim:.3f} "
          f"→ skill {report['brier_skill_vs_climatology']:+.0%}")
    print("[RISK] Calibration (score → what actually happened):")
    for b in report["reliability"]:
        print(f"[RISK]   score {b['bin']:>7}: n={b['n']:5d}  mean score {b['mean_score']:5.1f}  "
              f"hazard happened {b['observed_rate_pct']:5.1f}%")
    print("[RISK] Bands:")
    for b in bands:
        rate = f"{b['observed_hazard_rate_pct']:.0f}%" if b["observed_hazard_rate_pct"] is not None else "—"
        print(f"[RISK]   {b['band']:9s} {b['score_range']:>7}  {b['share_of_cases_pct']:4.1f}% of cases  "
              f"hazard rate {rate}")
    print(f"[RISK] Safety rules: {rule_checks}")
    print(f"[RISK] Floors (from tuning year): {fold_info[-1]['floors'] if fold_info else {}}")


if __name__ == "__main__":
    run()
