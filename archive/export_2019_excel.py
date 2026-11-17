"""
Excel workbook with only the 2019 test year: every prediction, its outcome
(correct alert, false positive, false negative, correct quiet), the Climb Risk
Score, and the 2019 samples.

    python -m archive.export_2019_excel   # → data/archive/results/SummitSathi_2019_Test_Data.xlsx
"""
import json
import sqlite3
from pathlib import Path
import sys

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.workbook.properties import CalcProperties
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import PatternFill

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import DB_PATH
from archive.evaluate import RESULTS_DIR, build_dataset
from archive.evaluate_v3 import add_cooling_features
from archive.export_excel import (header, title, write_table, F_BODY, F_HEAD, F_NOTE, F_INPUT, F_LINK,
                                  FILL_HEAD, PCT, DEC2, DEC1, INT)
from archive.truth import locations

OUT = RESULTS_DIR / "SummitSathi_2019_Test_Data.xlsx"
GROUP = "2018-2019"
HAZARDS = [("thunder_now", "Thunderstorm now"), ("rain_next3h", "Rain within 3 hours"),
           ("rain_now", "Rain now"), ("fog_now", "Fog now")]


def aligned_test_rows(data, ev):
    """Rebuild the order evaluate_v3 used for this hazard's 2019 test rows."""
    rows = [r for r in data if r[ev] is not None]
    return [r for r in rows if r["time"].year in (2018, 2019)]


def main():
    metrics = json.loads((RESULTS_DIR / "metrics_v3.json").read_text())
    preds = json.loads((RESULTS_DIR / "predictions_v3.json").read_text())
    rpred = json.loads((RESULTS_DIR / "risk_predictions_v3.json").read_text())
    test = json.loads((RESULTS_DIR / "test_2019.json").read_text())
    locs = locations()
    data = build_dataset()
    add_cooling_features(data)

    # Align saved predictions with their cases and prove the alignment
    per_ev = {}
    for ev, _ in HAZARDS:
        d = preds[ev]
        k = np.array(d["group"]) == GROUP
        y_saved = np.array(d["y"])[k]
        p_saved = np.array(d["p"])[k]
        rows = aligned_test_rows(data, ev)
        y_rebuilt = np.array([int(bool(r[ev])) for r in rows])
        if len(rows) != len(y_saved) or not (y_rebuilt == y_saved).all():
            raise SystemExit(f"Alignment check failed for {ev}")
        fold = [f for f in metrics["events"][ev]["folds"] if f["test_years"] == [2018, 2019]][0]
        per_ev[ev] = {"rows": rows, "y": y_saved, "p": p_saved, "thr": fold["thresholds"]}
    base_rows = per_ev["thunder_now"]["rows"]
    for ev, _ in HAZARDS:
        if [(r["obs_id"], r["location"]) for r in per_ev[ev]["rows"]] != \
           [(r["obs_id"], r["location"]) for r in base_rows]:
            raise SystemExit(f"Row order differs for {ev}")
    print(f"[2019] Alignment verified for all hazards: {len(base_rows)} cases")

    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    n = len(base_rows)
    first, last = 4, 3 + n

    # ── Read Me ───────────────────────────────────────────────
    ws = wb.active
    ws.title = "Read Me"
    title(ws, "SummitSathi — 2019 test year only",
          "The model was trained on 2020–2025 (2020 also used for tuning) and tested once on these 2019 cases.")
    rows = [
        ("Sheet", "What it contains"),
        ("Summary", "Results per hazard. Alert thresholds are inputs (blue); the counts of correct alerts, false "
                    "positives, false negatives and correct quiets are formulas over 'Hazard Predictions'."),
        ("Hazard Predictions", "All 2,860 test cases: SummitSathi's probability for each hazard, whether it alerted "
                               "(formula), what the airport reported (1/0) and the outcome (formula)."),
        ("Risk Predictions", "The Climb Risk Score for each 2019 case, its band (formula) and whether a hazard was reported."),
        ("Risk Bands", "Cases, hazards and hazard rate per band (formulas), with the false negatives and false positives."),
        ("Calibration", "Score given against hazard rate, in 10-point bins (formulas)."),
        ("Samples 2019", "Every 2019 satellite–weather match with all satellite measurements and the airport report."),
        ("", ""),
        ("Correct alert", "SummitSathi alerted and the hazard was reported (true positive)."),
        ("False positive", "SummitSathi alerted but no hazard was reported (false alarm)."),
        ("False negative", "A hazard was reported but SummitSathi did not alert (missed)."),
        ("Correct quiet", "No alert and no hazard (true negative)."),
        ("Hiker-safety setting", "Alert threshold chosen on 2020 data to miss as few hazards as possible."),
        ("Balanced setting", "Alert threshold chosen on 2020 data to balance catches and false alarms."),
        ("AUC", "Chance that SummitSathi scores a real hazard above a calm moment; 0.5 = coin toss, 1.0 = perfect."),
        ("", ""),
        ("Colour key", "Blue = inputs you can change. Green = formulas reading another sheet. Black = study values."),
        ("Calculation", "Formulas recalculate when opened in Excel (click Enable Editing if asked)."),
    ]
    for r, (a, b) in enumerate(rows, 4):
        ws.cell(row=r, column=1, value=a).font = F_HEAD if r == 4 or a in ("Correct alert",) and False else F_BODY
        ws.cell(row=r, column=2, value=b).font = F_BODY
        ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws["A4"].font = ws["B4"].font = F_HEAD
    ws["A4"].fill = ws["B4"].fill = FILL_HEAD
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 105

    # ── Hazard Predictions ────────────────────────────────────
    wp = wb.create_sheet("Hazard Predictions")
    title(wp, "Every 2019 test case: prediction, alert and outcome",
          "Alert = probability at or above the threshold on the Summary sheet (hiker-safety setting by default).")
    cols = ["Pass ID", "Airport", "Airport name", "Pass time (UTC)", "Satellite"]
    for _, name in HAZARDS:
        cols += [f"{name}: probability", f"{name}: alert (1/0)", f"{name}: reported (1/0)", f"{name}: outcome"]
    table_rows = []
    for i, r in enumerate(base_rows):
        row = [r["obs_id"], r["location"], locs.get(r["location"], {}).get("name", "").title(),
               r["time"].strftime("%Y-%m-%d %H:%M:%S"), r["satellite"]]
        for ev, _ in HAZARDS:
            row += [round(float(per_ev[ev]["p"][i]), 4), None, int(per_ev[ev]["y"][i]), None]
        table_rows.append(row)
    write_table(wp, 3, cols, table_rows, widths=[11, 8, 18, 18, 9] + [12, 9, 10, 15] * 4)
    from openpyxl.utils import get_column_letter as L
    for h, (ev, _) in enumerate(HAZARDS):
        pc, ac, yc, oc = (L(6 + 4 * h + j) for j in range(4))
        thr = f"Summary!$C${6 + h}"
        for rr in range(first, last + 1):
            wp[f"{ac}{rr}"] = f"=IF({pc}{rr}>={thr},1,0)"
            wp[f"{oc}{rr}"] = (f'=IF(AND({ac}{rr}=1,{yc}{rr}=1),"Correct alert",IF(AND({ac}{rr}=1,{yc}{rr}=0),'
                               f'"False positive",IF(AND({ac}{rr}=0,{yc}{rr}=1),"False negative","Correct quiet")))')
            wp[f"{ac}{rr}"].font = wp[f"{oc}{rr}"].font = F_BODY
        for txt, color in (("False positive", "FDEEE8"), ("False negative", "FFF4CC")):
            wp.conditional_formatting.add(f"{oc}{first}:{oc}{last}",
                                          FormulaRule(formula=[f'{oc}{first}="{txt}"'],
                                                      fill=PatternFill("solid", fgColor=color)))

    # ── Summary ───────────────────────────────────────────────
    wsum = wb.create_sheet("Summary", 1)
    title(wsum, "2019 test year: results per hazard",
          "Thresholds (blue) are the hiker-safety settings fixed on 2020 data. Change one to see the trade-off. "
          "AUC values come from the study (metrics_v3.json).")
    hdr = ["Hazard", "Test cases", "Alert threshold (probability)", "Balanced threshold (reference)",
           "Reported hazards", "Correct alerts", "False positives", "False negatives", "Correct quiets",
           "Caught (correct ÷ reported)", "Alerts correct (correct ÷ alerts)", "SummitSathi AUC",
           "Local history AUC", "Satellite-only AUC"]
    header(wsum, 5, hdr, [20, 10, 14, 14, 11, 11, 11, 11, 11, 13, 14, 10, 11, 11])
    for h, (ev, name) in enumerate(HAZARDS):
        r = 6 + h
        ac, yc, oc = (L(6 + 4 * h + j) for j in (1, 2, 3))
        rng = lambda c: f"'Hazard Predictions'!${c}${first}:${c}${last}"
        e = test["events"][ev]
        vals = [name, f"=COUNTA({rng('A')})", round(per_ev[ev]["thr"]["safety"], 4),
                round(per_ev[ev]["thr"]["best_f1"], 4), f"=SUM({rng(yc)})",
                f'=COUNTIF({rng(oc)},"Correct alert")', f'=COUNTIF({rng(oc)},"False positive")',
                f'=COUNTIF({rng(oc)},"False negative")', f'=COUNTIF({rng(oc)},"Correct quiet")',
                f"=IFERROR(F{r}/E{r},0)", f"=IFERROR(F{r}/(F{r}+G{r}),0)",
                round(e["auc"], 3), round(e["clim"], 3), round(e["sat"], 3)]
        fmts = [None, INT, "0.0000", "0.0000", INT, INT, INT, INT, INT, PCT, PCT, DEC2, DEC2, DEC2]
        for c, (v, f) in enumerate(zip(vals, fmts), 1):
            cell = wsum.cell(row=r, column=c, value=v)
            cell.font = F_INPUT if c == 3 else F_LINK if isinstance(v, str) and v.startswith("=") else F_BODY
            if f:
                cell.number_format = f
    wsum["A11"] = ("Thunderstorm example: of the reported thunderstorms, 'Caught' is the share SummitSathi alerted on; "
                   "'False negatives' are the ones it missed; 'False positives' are alerts with no storm.")
    wsum["A11"].font = F_NOTE
    wsum.freeze_panes = "B6"

    # ── Risk Predictions ──────────────────────────────────────
    wr = wb.create_sheet("Risk Predictions")
    title(wr, "Climb Risk Score for every 2019 test case",
          "Hazard reported: 1 = thunderstorm now, rain within 3 h or fog reported at the airport.")
    k = [i for i, g in enumerate(rpred["group"]) if g == GROUP]
    rows = []
    for i in k:
        m = rpred["meta"][i]
        rows.append([m["obs_id"], m["location"], locs.get(m["location"], {}).get("name", "").title(),
                     m["time"].replace("T", " "), round(rpred["score"][i], 1), None, int(rpred["y"][i]),
                     round(rpred["baseline"][i], 1)])
    write_table(wr, 3, ["Pass ID", "Airport", "Airport name", "Pass time (UTC)", "Climb Risk Score", "Band",
                        "Hazard reported (1/0)", "Local-history score"], rows, {5: DEC1, 8: DEC1},
                [11, 8, 20, 18, 12, 11, 12, 13])
    r_last = 3 + len(rows)
    for rr in range(4, r_last + 1):
        wr[f"F{rr}"] = (f'=IF(E{rr}>=70,"EXTREME",IF(E{rr}>=45,"HIGH",IF(E{rr}>=25,"MODERATE",'
                        f'IF(E{rr}>=10,"LOW","MINIMAL"))))')
        wr[f"F{rr}"].font = F_BODY
    SC, HZ = f"'Risk Predictions'!$E$4:$E${r_last}", f"'Risk Predictions'!$G$4:$G${r_last}"

    # ── Risk Bands ────────────────────────────────────────────
    wbd = wb.create_sheet("Risk Bands")
    title(wbd, "Climb Risk bands on 2019 — what actually happened",
          "False negatives here = hazards in a low band; false positives = no hazard in a high band.")
    header(wbd, 4, ["Band", "Score from (≥)", "Score to (<)", "Cases", "Hazard happened", "Hazard rate",
                    "No hazard", "Share of all cases", "Reading"], [11, 12, 11, 9, 13, 11, 10, 13, 48])
    bands = [("Minimal", 0, 10, "Hazards here are false negatives (score said fine)"),
             ("Low", 10, 25, ""), ("Moderate", 25, 45, ""),
             ("High", 45, 70, "No-hazard cases here are false positives"),
             ("Extreme", 70, 101, "No-hazard cases here are false positives (score said danger)")]
    for i, (name, lo, hi, note) in enumerate(bands):
        r = 5 + i
        wbd.cell(row=r, column=1, value=name).font = F_BODY
        wbd.cell(row=r, column=2, value=lo).font = F_INPUT
        wbd.cell(row=r, column=3, value=hi).font = F_INPUT
        wbd.cell(row=r, column=4, value=f'=COUNTIFS({SC},">="&B{r},{SC},"<"&C{r})').font = F_LINK
        wbd.cell(row=r, column=5, value=f'=COUNTIFS({SC},">="&B{r},{SC},"<"&C{r},{HZ},1)').font = F_LINK
        c = wbd.cell(row=r, column=6, value=f"=IFERROR(E{r}/D{r},0)"); c.number_format = PCT
        wbd.cell(row=r, column=7, value=f"=D{r}-E{r}").font = F_BODY
        c = wbd.cell(row=r, column=8, value=f"=IFERROR(D{r}/SUM($D$5:$D$9),0)"); c.number_format = PCT
        wbd.cell(row=r, column=9, value=note).font = F_BODY
    wbd["A10"], wbd["D10"], wbd["E10"], wbd["G10"] = "Total", "=SUM(D5:D9)", "=SUM(E5:E9)", "=SUM(G5:G9)"
    wbd["F10"] = "=IFERROR(E10/D10,0)"; wbd["F10"].number_format = PCT
    for c in ("A10", "D10", "E10", "F10", "G10"):
        wbd[c].font = F_HEAD
    wbd["A12"] = "Extreme's upper limit is 101 so that a score of exactly 100 is included."
    wbd["A12"].font = F_NOTE

    # ── Calibration ───────────────────────────────────────────
    wc = wb.create_sheet("Calibration")
    title(wc, "Is the score honest? 2019 test year",
          "An honest score has 'Average score given' close to 'Hazard rate (%)' in every row.")
    header(wc, 4, ["Score from (≥)", "Score to (<)", "Cases", "Average score given", "Hazards", "Hazard rate (%)"],
           [13, 12, 9, 16, 10, 14])
    for i in range(10):
        r = 5 + i
        wc.cell(row=r, column=1, value=10 * i).font = F_INPUT
        wc.cell(row=r, column=2, value=101 if i == 9 else 10 * (i + 1)).font = F_INPUT
        wc.cell(row=r, column=3, value=f'=COUNTIFS({SC},">="&A{r},{SC},"<"&B{r})').font = F_LINK
        c = wc.cell(row=r, column=4, value=f'=IFERROR(AVERAGEIFS({SC},{SC},">="&A{r},{SC},"<"&B{r}),"")')
        c.font, c.number_format = F_LINK, DEC1
        wc.cell(row=r, column=5, value=f'=COUNTIFS({SC},">="&A{r},{SC},"<"&B{r},{HZ},1)').font = F_LINK
        c = wc.cell(row=r, column=6, value=f'=IFERROR(100*E{r}/C{r},"")'); c.number_format = DEC1

    # ── Samples 2019 ──────────────────────────────────────────
    wsm = wb.create_sheet("Samples 2019")
    title(wsm, "Every 2019 satellite–weather match", "Temperatures in kelvin. TRUE/FALSE columns are airport observations.")
    d19 = sorted([d for d in data if d["time"].year == 2019], key=lambda x: (x["time"], x["location"]))
    skip = {"v1", "channel_b"}
    keys = sorted({k for d in d19 for k in d["features"] if k not in skip})
    cols = ["Pass ID", "Airport", "Pass time (UTC)", "Satellite"] + keys + \
           ["METAR thunderstorm", "METAR rain", "METAR fog", "METAR rain within 3 h", "METAR max cloud (oktas)",
            "METAR min visibility (m)"]
    rows = []
    for d in d19:
        f, m = d["features"], d["metar"] or {}
        rows.append([d["obs_id"], d["location"], d["time"].strftime("%Y-%m-%d %H:%M:%S"), d["satellite"]] +
                    [round(f[k], 4) if isinstance(f.get(k), float) else f.get(k) for k in keys] +
                    [m.get("thunder"), m.get("rain"), m.get("fog"), m.get("rain_next3h"), m.get("oktas_max"),
                     m.get("vis_min_m")])
    write_table(wsm, 3, cols, rows, widths=[11, 8, 18, 9] + [11] * (len(cols) - 4))

    wb._sheets = [wb[s] for s in ("Read Me", "Summary", "Hazard Predictions", "Risk Predictions",
                                  "Risk Bands", "Calibration", "Samples 2019")]
    wb.save(OUT)
    print(f"[2019] {OUT} ({OUT.stat().st_size / 1e6:.1f} MB); {n} test cases, {len(rows)} samples")


if __name__ == "__main__":
    main()
