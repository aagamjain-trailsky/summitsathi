"""
v3: gradient-boosted trees on satellite features (cloud-top temperature,
storm structure, visible brightness, night fog, cooling rate between passes)
plus the airport's own climate history, with alert thresholds tuned for
hiker safety.

Protocol — leave-one-year-out, because clean passes are concentrated in
2019–2021 (2022–25 SatNOGS images are mostly too noisy to use):
  tune       the 2020 passes choose model settings and alert thresholds
  test       each test group is predicted by a model trained on all OTHER
             years; the airport climate history used as an input also
             excludes the test years. Every sample outside 2020 is therefore
             predicted by a model that never saw its year.

    python -m archive.evaluate_v3
"""
import json
import pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.evaluate import (build_dataset, climatology, auc, confusion, bootstrap_f1,
                              best_threshold, RESULTS_DIR, FEATURES, CLIM_FEATURES, EVENTS)
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score

TUNE_YEARS = {2020}
TEST_GROUPS = [{2018, 2019}, {2021}, {2022, 2023, 2024, 2025}]
ALL_TIME = datetime(2027, 1, 1)      # climatology uses every year not excluded
SAFETY_RECALL = 0.80          # safety threshold: catch at least this share of events
V3_EVENTS = ["thunder_now", "rain_now", "rain_next3h", "fog_now"]

STRUCTURE = ["bt_min_50km", "bt_min_100km", "bt_std_50km", "bt_std_100km",
             "frac_lt_233_50km", "frac_lt_233_100km", "frac_lt_253_50km", "frac_lt_253_100km",
             "ot_count_50km", "ot_count_100km", "bt_grad_mean", "bt_grad_max"]
VISIBLE = ["vis_refl_mean", "vis_refl_p90", "frac_bright_cold", "frac_dim_cold"]
COOLING = ["has_prev", "prev_gap_h", "d_bt_min_per_h", "d_bt_min_100km_per_h",
           "d_frac_lt_233_100km_per_h"]
V3_SATELLITE = FEATURES + ["btd_p90"] + STRUCTURE + VISIBLE + COOLING
V3_FEATURES = V3_SATELLITE + CLIM_FEATURES

GRID = [{"max_depth": d, "learning_rate": lr, "class_weight": cw}
        for d in (3, 5) for lr in (0.05, 0.1) for cw in (None, "balanced")]


# ── Cooling rate between passes ────────────────────────────────
def add_cooling_features(data: list, max_gap_h: float = 4.0, min_gap_h: float = 0.3):
    """Compare each sample with the previous pass over the same airport
    (another satellite, within a few hours). Cloud tops getting colder
    quickly means a storm is growing."""
    by_loc = {}
    for r in data:
        by_loc.setdefault(r["location"], []).append(r)
    for rows in by_loc.values():
        rows.sort(key=lambda r: r["time"])
        for k, r in enumerate(rows):
            f = r["features"]
            f["has_prev"] = 0.0
            for prev in reversed(rows[:k]):
                gap = (r["time"] - prev["time"]).total_seconds() / 3600
                if gap > max_gap_h:
                    break
                if gap < min_gap_h or prev["obs_id"] == r["obs_id"]:
                    continue
                pf = prev["features"]
                f["has_prev"] = 1.0
                f["prev_gap_h"] = gap
                for key, out in (("bt_min", "d_bt_min_per_h"),
                                 ("bt_min_100km", "d_bt_min_100km_per_h"),
                                 ("frac_lt_233_100km", "d_frac_lt_233_100km_per_h")):
                    if key in f and key in pf:
                        f[out] = (f[key] - pf[key]) / gap
                break


def matrix(rows, features) -> np.ndarray:
    return np.array([[r["features"].get(k, np.nan) for k in features] for r in rows], float)

def safety_threshold(y, p, target=SAFETY_RECALL) -> float:
    """Highest probability threshold that still catches `target` of events."""
    y = np.asarray(y, bool)
    if y.sum() == 0:
        return 0.5
    return float(np.quantile(p[y], 1 - target))


def _hgb(cfg):
    return HistGradientBoostingClassifier(max_iter=300, l2_regularization=1.0,
                                          early_stopping=False, random_state=0, **cfg)

def set_climatology(rows, exclude_years):
    for ev_flag, feat in (("rain_now", "clim_rain"), ("thunder_now", "clim_thunder"),
                          ("fog_now", "clim_fog"), ("cloudy_now", "clim_cloudy")):
        for r, v in zip(rows, climatology(rows, ev_flag, ALL_TIME, exclude_years)):
            r["features"][feat] = float(v)

def run_fold(ev, train, tune, test, features):
    """Choose settings + thresholds on the tuning year, then refit on all
    training years (tuning year included) and predict the test group."""
    inner = [r for r in train if r["time"].year not in TUNE_YEARS]
    y_in = np.array([r[ev] for r in inner], bool)
    y_tu = np.array([r[ev] for r in tune], bool)
    X_in, X_tu = matrix(inner, features), matrix(tune, features)

    tried = []
    for cfg in GRID:
        p = _hgb(cfg).fit(X_in, y_in).predict_proba(X_tu)[:, 1]
        tried.append({**cfg, "tune_auc": auc(y_tu, p),
                      "tune_avg_precision": float(average_precision_score(y_tu, p))})
    best = max(tried, key=lambda t: t["tune_avg_precision"])
    cfg = {k: best[k] for k in ("max_depth", "learning_rate", "class_weight")}

    m_in = _hgb(cfg).fit(X_in, y_in)
    p_tu = m_in.predict_proba(X_tu)[:, 1]
    thresholds = {"best_f1": best_threshold(y_tu, p_tu), "safety": safety_threshold(y_tu, p_tu)}

    y_tr = np.array([r[ev] for r in train], bool)
    final = _hgb(cfg).fit(matrix(train, features), y_tr)
    p_te = final.predict_proba(matrix(test, features))[:, 1]
    return {"cfg": cfg, "tried": tried, "thresholds": thresholds, "p_test": p_te,
            "model": final, "inner_model": m_in, "X_tune": X_tu, "y_tune": y_tu}


def evaluate():
    data = build_dataset()
    add_cooling_features(data)
    years = sorted({r["time"].year for r in data})
    print(f"[V3] {len(data)} samples, years {years}, "
          f"{sum(r['features']['has_prev'] for r in data):.0f} with a previous pass for cooling rate")

    report = {"protocol": "leave-one-year-out; settings and thresholds tuned on 2020",
              "tune_years": sorted(TUNE_YEARS), "test_groups": [sorted(g) for g in TEST_GROUPS],
              "n_samples": len(data), "events": {}}
    models = {}

    for ev in V3_EVENTS:
        rows = [r for r in data if r[ev] is not None]
        tune = [r for r in rows if r["time"].year in TUNE_YEARS]
        y_all, p_all, p_sat, p_clim, groups, fold_info = [], [], [], [], [], []
        alerts_f1, alerts_safe = [], []
        importances = []

        for g in TEST_GROUPS:
            test = [r for r in rows if r["time"].year in g]
            train = [r for r in rows if r["time"].year not in g]
            inner = [r for r in train if r["time"].year not in TUNE_YEARS]
            if (not test or sum(r[ev] for r in test) == 0 or not tune or not inner
                    or sum(r[ev] for r in tune) == 0 or sum(r[ev] for r in inner) == 0):
                print(f"[V3] {ev}: fold {sorted(g)} skipped — missing training, tuning or test events")
                continue
            set_climatology(rows, g)          # history never includes the test years
            res = run_fold(ev, train, tune, test, V3_FEATURES)
            sat = run_fold(ev, train, tune, test, V3_SATELLITE)
            y = [r[ev] for r in test]
            y_all += y
            p_all += list(res["p_test"])
            p_sat += list(sat["p_test"])
            p_clim += list(climatology(test, ev, ALL_TIME, g))
            groups += ["-".join(map(str, sorted(g)))] * len(test)
            alerts_f1 += list(res["p_test"] >= res["thresholds"]["best_f1"])
            alerts_safe += list(res["p_test"] >= res["thresholds"]["safety"])
            imp = permutation_importance(res["inner_model"], res["X_tune"], res["y_tune"],
                                         scoring="average_precision", n_repeats=5, random_state=0)
            importances.append(imp.importances_mean)
            fold_info.append({"test_years": sorted(g), "n": len(test), "events": int(sum(y)),
                              "settings": res["cfg"], "thresholds": res["thresholds"],
                              "auc": auc(y, res["p_test"]),
                              "configs_tried": res["tried"]})
            models[ev] = {"model": res["model"], "features": V3_FEATURES,
                          "thresholds": res["thresholds"]}

        if sum(y_all) < 10:
            report["events"][ev] = {"skipped": f"only {sum(y_all)} events in test data"}
            print(f"[V3] {ev}: skipped — only {sum(y_all)} events")
            continue

        y_all, p_all = np.array(y_all, bool), np.array(p_all)
        a_f1, a_safe = np.array(alerts_f1), np.array(alerts_safe)
        imp_mean = np.mean(importances, axis=0)
        report["events"][ev] = {
            "test_n": int(len(y_all)), "test_events": int(y_all.sum()),
            "auc": auc(y_all, p_all),
            "avg_precision": float(average_precision_score(y_all, p_all)),
            "satellite_only_auc": auc(y_all, np.array(p_sat)),
            "climatology_auc": auc(y_all, np.array(p_clim)),
            "best_f1": {**confusion(y_all, a_f1), "f1_ci95": bootstrap_f1(y_all, a_f1)},
            "safety": {**confusion(y_all, a_safe), "f1_ci95": bootstrap_f1(y_all, a_safe)},
            "top_features": sorted(zip(V3_FEATURES, map(float, imp_mean)), key=lambda x: -x[1])[:10],
            "folds": fold_info,
        }
        # Keep pooled predictions for charts
        report["events"][ev]["_pred"] = {"y": y_all.astype(int).tolist(), "p": p_all.tolist(),
                                         "p_sat": list(map(float, p_sat)),
                                         "p_clim": list(map(float, p_clim)), "group": groups}

    preds = {ev: r.pop("_pred") for ev, r in report["events"].items() if "_pred" in r}
    (RESULTS_DIR / "metrics_v3.json").write_text(json.dumps(report, indent=1, default=str))
    (RESULTS_DIR / "predictions_v3.json").write_text(json.dumps(preds))
    with open(RESULTS_DIR / "model_v3.pkl", "wb") as f:
        pickle.dump(models, f)
    print_summary(report)


def print_summary(report):
    print(f"\n[V3] ── Out-of-year test results ({report['protocol']}) ──")
    for ev, r in report["events"].items():
        if "skipped" in r:
            print(f"[V3] {ev}: {r['skipped']}")
            continue
        print(f"[V3] {ev}: test n={r['test_n']}, events={r['test_events']} "
              f"({r['test_events'] / r['test_n']:.0%})")
        print(f"[V3]   AUC {r['auc']:.2f}  (satellite only {r['satellite_only_auc']:.2f}, "
              f"local history only {r['climatology_auc']:.2f})")
        for name in ("best_f1", "safety"):
            x = r[name]
            print(f"[V3]   {name:8s} F1 {x['f1']:.2f} [{x['f1_ci95'][0]:.2f}–{x['f1_ci95'][1]:.2f}]  "
                  f"catches {x['recall']:.0%}  right when it fires {x['precision']:.0%}")
        print("[V3]   per test group AUC: " + ", ".join(
            f"{'-'.join(map(str, f['test_years']))}: {f['auc']:.2f} (n={f['n']})" for f in r["folds"]))
        print("[V3]   top features: " + ", ".join(k for k, _ in r["top_features"][:5]))


if __name__ == "__main__":
    evaluate()
