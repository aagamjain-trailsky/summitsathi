"""
Export every result and every data point to one Excel workbook.

    python -m archive.export_excel        # → data/archive/results/TrailSky_Archive_Data.xlsx
"""
import json
import sqlite3
from pathlib import Path
import sys

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.db import DB_PATH
from archive.evaluate import RESULTS_DIR, build_dataset
from archive.evaluate_v3 import add_cooling_features
from archive.truth import locations

OUT = RESULTS_DIR / "TrailSky_Archive_Data.xlsx"

FONT = "Arial"
F_BODY = Font(name=FONT, size=10)
F_HEAD = Font(name=FONT, size=10, bold=True)
F_TITLE = Font(name=FONT, size=14, bold=True)
F_NOTE = Font(name=FONT, size=9, italic=True, color="595959")
F_INPUT = Font(name=FONT, size=10, color="0000FF")          # hard-coded inputs
F_LINK = Font(name=FONT, size=10, color="008000")           # formulas pulling from another sheet
FILL_HEAD = PatternFill("solid", fgColor="F2F2F2")
RULE = Border(bottom=Side(style="thin", color="808080"))
PCT, DEC2, DEC1, INT = "0.0%", "0.00", "0.0", "#,##0"

EVENT_NAME = {"thunder_now": "Thunderstorm (now)", "rain_next3h": "Rain within 3 hours",
              "rain_now": "Rain (now)", "fog_now": "Fog (now)"}


def header(ws, row, names, widths=None):
    for c, name in enumerate(names, 1):
        cell = ws.cell(row=row, column=c, value=name)
        cell.font, cell.fill, cell.border = F_HEAD, FILL_HEAD, RULE
        cell.alignment = Alignment(wrap_text=True, vertical="bottom")
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w

def title(ws, text, note=None):
    ws["A1"] = text
    ws["A1"].font = F_TITLE
    if note:
        ws["A2"] = note
        ws["A2"].font = F_NOTE

def body_font(ws, first_row):
    for row in ws.iter_rows(min_row=first_row):
        for c in row:
            if c.font == Font() or c.font.name != FONT:
                c.font = F_BODY

def write_table(ws, start_row, columns, rows, formats=None, widths=None):
    header(ws, start_row, columns, widths)
    for r, values in enumerate(rows, start_row + 1):
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = F_BODY
            if formats and formats.get(c):
                cell.number_format = formats[c]
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    last = get_column_letter(len(columns))
    ws.auto_filter.ref = f"A{start_row}:{last}{start_row + max(len(rows), 1)}"


def main():
    metrics = json.loads((RESULTS_DIR / "metrics_v3.json").read_text())
    risk = json.loads((RESULTS_DIR / "risk_v3.json").read_text())
    rpred = json.loads((RESULTS_DIR / "risk_predictions_v3.json").read_text())
    geo_val = json.loads((RESULTS_DIR / "geo_validation.json").read_text())["summary"]
    locs = locations()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)

    # ── Read Me ───────────────────────────────────────────────
    ws = wb.active
    ws.title = "Read Me"
    title(ws, "TrailSky archive study — data workbook",
          "Real NOAA-15/18/19 APT satellite passes over India (2018–2025) scored against airport weather reports.")
    readme = [
        ("Sheet", "What it contains"),
        ("Summary", "v3 results for each hazard and the Climb Risk Score headline figures."),
        ("Risk Bands", "Climb Risk bands. Counts and hazard rates are Excel formulas over 'Risk Predictions', so they can be checked."),
        ("Calibration", "Score bins 0–10 … 90–100: average score given vs share of cases where a hazard was reported (formulas)."),
        ("Risk Predictions", "Every out-of-year Climb Risk Score: one row per pass × airport, with what actually happened."),
        ("Samples", "Every satellite–weather match: satellite features at the airport plus the airport's METAR report and ERA5."),
        ("Passes", "Every downloaded satellite pass, its quality, and whether it was usable."),
        ("Airports", "The 44 airports used as sample locations, with the number of samples at each (formula)."),
        ("Stations", "SatNOGS ground stations: image-quality screening and measured timing offsets."),
        ("Model Settings", "Every model configuration tried during tuning, with its tuning-year score."),
        ("Safety Rules", "Rules that keep the score at High or above near storm cloud, and how they performed."),
        ("", ""),
        ("Definitions", ""),
        ("Out-of-year test", "Each year is predicted by a model trained without that year (leave-one-year-out). "
                             "2020 is used only to tune settings and thresholds."),
        ("Hazard", "A thunderstorm reported now, rain reported within the next 3 hours, or fog reported now, "
                   "at the airport, from METAR reports within ±1 hour of the pass."),
        ("Climb Risk Score", "Calibrated chance (0–100) that a hazard is reported. A score of 30 should mean about 30%."),
        ("AUC", "How well a score ranks real events above non-events. 0.5 = coin toss, 1.0 = perfect."),
        ("Brier score", "Average squared error of a probability. Lower is better."),
        ("Climate history baseline", "How often the hazard is reported at that airport in that month and 3-hour time block, "
                                     "from METAR reports of all other years."),
        ("Brightness temperature (K)", "Cloud-top temperature from the 11 µm channel. Subtract 273.15 for °C. "
                                       "Below 233 K (−40 °C) indicates deep storm cloud."),
        ("Fog signal (K)", "11 µm minus 3.7 µm temperature at night. Positive values indicate fog or low cloud."),
        ("", ""),
        ("Colour key", "Blue text = typed-in input values. Green text = formulas that read another sheet. Black = values from the study."),
        ("Calculation", "Formulas recalculate when the workbook is opened in Excel."),
        ("", ""),
        ("Sources", "SatNOGS Network (CC BY-SA 4.0): APT images and pass metadata · Iowa Environmental Mesonet: METAR archive · "
                    "ERA5 reanalysis via Open-Meteo · Natural Earth: coastlines."),
        ("Privacy", "No observer names or station names are stored. Locations are public airports."),
    ]
    for r, (a, b) in enumerate(readme, 4):
        ws.cell(row=r, column=1, value=a).font = F_HEAD if a and (r == 4 or b == "") else F_BODY
        ws.cell(row=r, column=2, value=b).font = F_BODY
        ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=r, column=1).alignment = Alignment(vertical="top")
    ws["A4"].fill = ws["B4"].fill = FILL_HEAD
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110

    # ── Risk Predictions (raw data the formulas read) ────────
    wp = wb.create_sheet("Risk Predictions")
    title(wp, "Climb Risk Score — every out-of-year prediction",
          "Band is a formula on the score. Hazard reported: 1 = thunderstorm now, rain within 3 h or fog now was reported.")
    n_pred = len(rpred["score"])
    rows = []
    for k in range(n_pred):
        meta = rpred["meta"][k]
        loc = locs.get(meta["location"], {})
        rows.append([meta["obs_id"], meta["location"], loc.get("name", "").title(),
                     meta["time"].replace("T", " "), rpred["group"][k],
                     round(rpred["score"][k], 1), None, int(rpred["y"][k]), round(rpred["baseline"][k], 1)])
    first = 4
    write_table(wp, first - 1,
                ["Pass ID", "Airport", "Airport name", "Pass time (UTC)", "Test years",
                 "Climb Risk Score", "Band", "Hazard reported (1/0)", "Climate-history baseline score"],
                rows, {6: DEC1, 9: DEC1}, [11, 9, 22, 18, 18, 12, 11, 12, 14])
    for r in range(first, first + n_pred):
        wp.cell(row=r, column=7, value=(f'=IF(F{r}>=70,"EXTREME",IF(F{r}>=45,"HIGH",'
                                        f'IF(F{r}>=25,"MODERATE",IF(F{r}>=10,"LOW","MINIMAL"))))')).font = F_BODY
    last_pred = first + n_pred - 1
    SC = f"'Risk Predictions'!$F${first}:$F${last_pred}"
    HZ = f"'Risk Predictions'!$H${first}:$H${last_pred}"
    BL = f"'Risk Predictions'!$I${first}:$I${last_pred}"

    # ── Risk Bands (formulas) ─────────────────────────────────
    wbnd = wb.create_sheet("Risk Bands", 1)
    title(wbnd, "Climb Risk bands — what actually happened",
          "Lower/upper score limits are inputs (blue). Every other number is calculated from 'Risk Predictions'.")
    header(wbnd, 4, ["Band", "Score from (≥)", "Score to (<)", "Cases", "Hazards reported",
                     "Hazard rate", "Share of all cases", "Advice shown to the trekker"],
           [12, 13, 12, 10, 14, 12, 14, 60])
    for i, b in enumerate(risk["bands"]):
        r = 5 + i
        lo, hi = map(int, b["score_range"].split("–"))
        hi = 101 if b["band"] == "EXTREME" else hi
        wbnd.cell(row=r, column=1, value=b["band"].title()).font = F_BODY
        for c, v in ((2, lo), (3, hi)):
            wbnd.cell(row=r, column=c, value=v).font = F_INPUT
        wbnd.cell(row=r, column=4, value=f'=COUNTIFS({SC},">="&B{r},{SC},"<"&C{r})').font = F_LINK
        wbnd.cell(row=r, column=5, value=f'=COUNTIFS({SC},">="&B{r},{SC},"<"&C{r},{HZ},1)').font = F_LINK
        wbnd.cell(row=r, column=6, value=f"=IFERROR(E{r}/D{r},0)").number_format = PCT
        wbnd.cell(row=r, column=7, value=f"=IFERROR(D{r}/SUM($D$5:$D$9),0)").number_format = PCT
        wbnd.cell(row=r, column=8, value=b["decision"]).font = F_BODY
    wbnd["A10"], wbnd["D10"], wbnd["E10"] = "Total", "=SUM(D5:D9)", "=SUM(E5:E9)"
    wbnd["F10"] = "=IFERROR(E10/D10,0)"
    wbnd["F10"].number_format = PCT
    for c in ("A10", "D10", "E10", "F10"):
        wbnd[c].font = F_HEAD
    wbnd["A12"] = ("Note: the EXTREME upper limit is 101 so that a score of exactly 100 is included. "
                   "Scores of 90–100 came true 84% of the time, so no score means certainty.")
    wbnd["A12"].font = F_NOTE
    body_font(wbnd, 5)

    # ── Calibration (formulas) ────────────────────────────────
    wc = wb.create_sheet("Calibration", 2)
    title(wc, "Is the score honest? Score given vs hazard actually reported",
          "A perfectly honest score has 'Average score given' ≈ 'Hazard rate (%)' in every row.")
    header(wc, 4, ["Score from (≥)", "Score to (<)", "Cases", "Average score given",
                   "Hazards reported", "Hazard rate (%)", "Gap (rate − score)"],
           [13, 12, 10, 16, 14, 14, 16])
    for i in range(10):
        r = 5 + i
        wc.cell(row=r, column=1, value=10 * i).font = F_INPUT
        wc.cell(row=r, column=2, value=101 if i == 9 else 10 * (i + 1)).font = F_INPUT
        wc.cell(row=r, column=3, value=f'=COUNTIFS({SC},">="&A{r},{SC},"<"&B{r})').font = F_LINK
        wc.cell(row=r, column=4, value=f'=IFERROR(AVERAGEIFS({SC},{SC},">="&A{r},{SC},"<"&B{r}),"")').font = F_LINK
        wc.cell(row=r, column=4).number_format = DEC1
        wc.cell(row=r, column=5, value=f'=COUNTIFS({SC},">="&A{r},{SC},"<"&B{r},{HZ},1)').font = F_LINK
        wc.cell(row=r, column=6, value=f'=IFERROR(100*E{r}/C{r},"")').number_format = DEC1
        wc.cell(row=r, column=7, value=f'=IFERROR(F{r}-D{r},"")').number_format = DEC1
    body_font(wc, 5)

    # ── Summary ───────────────────────────────────────────────
    wsum = wb.create_sheet("Summary", 1)
    title(wsum, "Results summary (out-of-year test)",
          f"Source: metrics_v3.json and risk_v3.json, produced by archive/evaluate_v3.py and archive/risk_v3.py. "
          f"Protocol: {metrics['protocol']}.")
    header(wsum, 4, ["Hazard", "Test cases", "Real events", "v3 AUC", "Satellite-only AUC",
                     "Climate-history AUC", "AUC gain over climate history",
                     "Caught (hiker-safety setting)", "Alerts correct (hiker-safety)",
                     "Caught (balanced setting)", "Alerts correct (balanced)",
                     "Balanced F1", "F1 95% CI low", "F1 95% CI high"],
           [22, 11, 11, 9, 12, 12, 14, 14, 14, 13, 13, 10, 10, 10])
    r = 5
    for ev in ("thunder_now", "rain_next3h", "rain_now", "fog_now"):
        e = metrics["events"].get(ev)
        if not e or "auc" not in e:
            continue
        vals = [EVENT_NAME[ev], e["test_n"], e["test_events"], e["auc"], e["satellite_only_auc"],
                e["climatology_auc"], f"=D{r}-F{r}", e["safety"]["recall"], e["safety"]["precision"],
                e["best_f1"]["recall"], e["best_f1"]["precision"], e["best_f1"]["f1"],
                e["best_f1"]["f1_ci95"][0], e["best_f1"]["f1_ci95"][1]]
        fmts = [None, INT, INT, DEC2, DEC2, DEC2, "+0.00;-0.00;0.00", PCT, PCT, PCT, PCT, DEC2, DEC2, DEC2]
        for c, (v, f) in enumerate(zip(vals, fmts), 1):
            cell = wsum.cell(row=r, column=c, value=v)
            cell.font = F_BODY
            if f:
                cell.number_format = f
        r += 1

    r += 1
    wsum.cell(row=r, column=1, value="Climb Risk Score").font = F_HEAD
    items = [
        ("Out-of-year predictions", f"=COUNT({SC})", INT, True),
        ("Hazards reported", f"=SUM({HZ})", INT, True),
        ("Hazard rate", f"=IFERROR(SUM({HZ})/COUNT({SC}),0)", PCT, True),
        ("AUC", risk["auc"], DEC2, False),
        ("Brier score — Climb Risk Score", f"=SUMPRODUCT(({SC}/100-{HZ})^2)/COUNT({SC})", "0.000", True),
        ("Brier score — climate history only", f"=SUMPRODUCT(({BL}/100-{HZ})^2)/COUNT({BL})", "0.000", True),
        ("Improvement over climate history", f"=1-B{r + 5}/B{r + 6}", PCT, False),
    ]
    for k, (label, val, fmt, link) in enumerate(items, 1):
        wsum.cell(row=r + k, column=1, value=label).font = F_BODY
        cell = wsum.cell(row=r + k, column=2, value=val)
        cell.number_format = fmt
        cell.font = F_LINK if link else F_BODY
    r += len(items) + 2
    wsum.cell(row=r, column=1, value="Data collected").font = F_HEAD
    n_pass = conn.execute("SELECT COUNT(*) FROM observations WHERE download_status='ok'").fetchone()[0]
    counts = [
        ("Satellite passes downloaded (all stations)", "=COUNTA(Passes!A4:A100000)", INT, True),
        ("…from stations producing real images", '=COUNTA(Passes!A4:A100000)-COUNTIF(Passes!L4:L100000,"station screened out*")', INT, True),
        ("Passes passing quality checks", '=COUNTIF(Passes!K4:K100000,"yes")+COUNTIF(Passes!L4:L100000,"no airport in clean part of swath")', INT, True),
        ("…of which produced at least one airport sample", '=COUNTIF(Passes!K4:K100000,"yes")', INT, True),
        ("Satellite–weather matches (samples)", "=COUNTA(Samples!A4:A100000)", INT, True),
        ("Airports", "=COUNTA(Airports!A4:A1000)", INT, True),
        ("Ground stations screened", "=COUNTA(Stations!A4:A1000)", INT, True),
        ("Median line-timing offset (s)", geo_val["median_offset_s"], DEC1, False),
    ]
    for k, (label, val, fmt, link) in enumerate(counts, 1):
        wsum.cell(row=r + k, column=1, value=label).font = F_BODY
        cell = wsum.cell(row=r + k, column=2, value=val)
        cell.number_format = fmt
        cell.font = F_LINK if link else F_BODY
    wsum.freeze_panes = "B5"

    # ── Samples ───────────────────────────────────────────────
    data = build_dataset()
    add_cooling_features(data)
    obs_meta = {r["obs_id"]: dict(r) for r in conn.execute(
        "SELECT obs_id, satellite, station_id, max_elev_deg FROM observations")}
    skip = {"v1", "channel_b"}
    feat_keys = sorted({k for d in data for k in d["features"] if k not in skip})
    first_keys = ["channel_a", "local_hour", "sun_zenith", "scan_angle", "bt_min", "bt_p10", "bt_p50",
                  "bt_mean", "bt_std", "frac_lt_273", "frac_lt_253", "frac_lt_233", "frac_lt_220",
                  "storm_dist_km", "bt_min_50km", "bt_min_100km", "ot_count_50km", "ot_count_100km"]
    feat_keys = [k for k in first_keys if k in feat_keys] + [k for k in feat_keys if k not in first_keys]
    truth_cols = ["METAR reports (±1 h)", "METAR thunderstorm", "METAR rain", "METAR fog", "METAR snow",
                  "METAR CB cloud", "METAR max cloud (oktas)", "METAR min visibility (m)",
                  "METAR rain within 3 h", "ERA5 cloud cover (%)", "ERA5 precipitation (mm/h)",
                  "ERA5 precipitation next 3 h (mm)", "ERA5 wind gust (km/h)"]
    wsm = wb.create_sheet("Samples")
    title(wsm, "Every satellite–weather match (one row per pass × airport)",
          "Satellite features are measured in a ~56 km box around the airport unless the column says otherwise. "
          "Temperatures in kelvin. TRUE/FALSE columns are airport observations.")
    cols = ["Pass ID", "Airport", "Pass time (UTC)", "Satellite", "Station ID", "Max elevation (°)"] \
           + feat_keys + truth_cols
    rows = []
    for d in sorted(data, key=lambda x: (x["time"], x["location"])):
        f, m, e = d["features"], d["metar"] or {}, d["era5"] or {}
        om = obs_meta.get(d["obs_id"], {})
        row = [d["obs_id"], d["location"], d["time"].strftime("%Y-%m-%d %H:%M:%S"), d["satellite"],
               om.get("station_id"), om.get("max_elev_deg")]
        for k in feat_keys:
            v = f.get(k)
            row.append(round(v, 4) if isinstance(v, float) else v)
        row += [m.get("n_reports"), m.get("thunder"), m.get("rain"), m.get("fog"), m.get("snow"),
                m.get("cb"), m.get("oktas_max"), m.get("vis_min_m"), m.get("rain_next3h"),
                e.get("cloud_cover"), e.get("precipitation"), e.get("precip_next3h"), e.get("wind_gusts_10m")]
        rows.append(row)
    write_table(wsm, 3, cols, rows, widths=[11, 8, 18, 9, 9, 10] + [11] * (len(cols) - 6))

    # ── Passes ────────────────────────────────────────────────
    wpa = wb.create_sheet("Passes")
    title(wpa, "Every downloaded satellite pass",
          "Usable = calibrated and at least one airport inside the clean part of the image.")
    with_samples = {r[0] for r in conn.execute("SELECT DISTINCT obs_id FROM samples")}
    rows = []
    bad_stations = {r[0] for r in conn.execute("SELECT station_id FROM station_quality WHERE verdict='bad'")}
    for o in conn.execute("""SELECT o.obs_id, o.satellite, o.start_utc, o.end_utc, o.max_elev_deg,
                                    o.station_id, i.n_lines, i.good_lines, i.channel_a, i.channel_b, i.error
                             FROM observations o LEFT JOIN images i USING (obs_id)
                             WHERE o.download_status = 'ok' ORDER BY o.start_utc"""):
        if o["station_id"] in bad_stations:
            reason = "station screened out (records noise only)"
        elif o["obs_id"] in with_samples:
            reason = ""
        else:
            reason = o["error"] or "no airport in clean part of swath"
        rows.append([o["obs_id"], o["satellite"], o["start_utc"].replace("T", " ").rstrip("Z"),
                     o["end_utc"].replace("T", " ").rstrip("Z"), o["max_elev_deg"], o["station_id"],
                     o["n_lines"], o["good_lines"], o["channel_a"], o["channel_b"],
                     "yes" if o["obs_id"] in with_samples else "no", reason])
    write_table(wpa, 3, ["Pass ID", "Satellite", "Start (UTC)", "End (UTC)", "Max elevation (°)",
                         "Station ID", "Image lines", "Clean lines", "Channel A", "Channel B",
                         "Usable", "Reason not usable"],
                rows, widths=[11, 9, 18, 18, 10, 9, 9, 9, 10, 10, 8, 34])

    # ── Airports ──────────────────────────────────────────────
    wa = wb.create_sheet("Airports")
    title(wa, "Sample locations (public airports with METAR reports)",
          "Samples and hazards are formulas over the 'Samples' and 'Risk Predictions' sheets.")
    loc_rows = sorted(locs.values(), key=lambda l: l["id"])
    write_table(wa, 3, ["ICAO", "Name", "Latitude (°N)", "Longitude (°E)", "Elevation (m)",
                        "Samples", "Out-of-year risk predictions", "Hazard rate in predictions"],
                [[l["id"], l["name"].title(), round(l["lat"], 3), round(l["lon"], 3),
                  round(l["elevation_m"]) if l.get("elevation_m") is not None else None, None, None, None]
                 for l in loc_rows], widths=[8, 26, 12, 13, 12, 10, 14, 14])
    for r in range(4, 4 + len(loc_rows)):
        wa.cell(row=r, column=6, value=f"=COUNTIF(Samples!$B$4:$B$100000,A{r})").font = F_LINK
        wa.cell(row=r, column=7, value=f"=COUNTIF('Risk Predictions'!$B${first}:$B${last_pred},A{r})").font = F_LINK
        c = wa.cell(row=r, column=8, value=(f"=IFERROR(SUMIFS({HZ},'Risk Predictions'!$B${first}:$B${last_pred},A{r})"
                                            f"/G{r},\"\")"))
        c.font, c.number_format = F_LINK, PCT

    # ── Stations ──────────────────────────────────────────────
    wst = wb.create_sheet("Stations")
    title(wst, "SatNOGS ground stations screened",
          "Image score = spread of column means; real APT images score about 5–50, pure noise about 2. "
          "Timing offsets measured from clear coastline matches; others use the median.")
    per = geo_val.get("per_station", {})
    rows = []
    for s in conn.execute("SELECT * FROM station_quality ORDER BY verdict DESC, best_score DESC"):
        p = per.get(str(s["station_id"]), {})
        n_used = conn.execute("""SELECT COUNT(DISTINCT s.obs_id) FROM samples s JOIN observations o
                                 USING (obs_id) WHERE o.station_id=?""", (s["station_id"],)).fetchone()[0]
        rows.append([s["station_id"], s["sampled"], s["with_signal"], round(s["best_score"], 1),
                     "real images" if s["verdict"] == "good" else "noise only — skipped",
                     p.get("median_offset_s"), p.get("strong", 0), n_used])
    write_table(wst, 3, ["Station ID", "Images sampled", "With real signal", "Best image score",
                         "Verdict", "Timing offset (s)", "Clear coastline matches", "Usable passes"],
                rows, {4: DEC1}, [10, 12, 12, 12, 22, 12, 14, 12])

    # ── Model Settings ────────────────────────────────────────
    wm = wb.create_sheet("Model Settings")
    title(wm, "Every configuration tried during tuning (gradient-boosted trees)",
          "Scored on the 2020 tuning year only; the configuration with the best average precision was kept.")
    rows = []
    for ev, e in metrics["events"].items():
        for fold in e.get("folds", []):
            chosen = fold["settings"]
            for t in fold["configs_tried"]:
                rows.append([EVENT_NAME.get(ev, ev), "-".join(map(str, fold["test_years"])),
                             t["max_depth"], t["learning_rate"], str(t["class_weight"]),
                             t["tune_auc"], t["tune_avg_precision"],
                             "yes" if all(t[k] == chosen[k] for k in chosen) else ""])
    write_table(wm, 3, ["Hazard", "Test years (held out)", "Tree depth", "Learning rate", "Class weight",
                        "Tuning AUC", "Tuning average precision", "Chosen"],
                rows, {6: "0.000", 7: "0.000"}, [22, 20, 10, 12, 12, 11, 14, 8])

    # ── Safety Rules ──────────────────────────────────────────
    wr = wb.create_sheet("Safety Rules")
    title(wr, "Safety rules on top of the model",
          "The minimum score was set from the 2020 tuning year; the hazard rate is measured on unseen years.")
    floors = risk["folds"][-1]["floors"] if risk["folds"] else {}
    names = {"storm_within_20km": "Storm cloud (< −40 °C) within 20 km",
             "overshooting_top_within_50km": "Overshooting storm top within 50 km"}
    rows = [[names[k], floors.get(k, {}).get("floor_score"), v["test_n"],
             (v["test_hazard_rate_pct"] or 0) / 100, v["times_applied"]]
            for k, v in risk["safety_rules"].items()]
    rows.append(["No usable satellite view of the position", "Shown as NO DATA (never 'safe')", None, None, None])
    rows.append([f"Latest pass older than {risk['stale_after_hours']:.0f} hours", "Marked STALE", None, None, None])
    write_table(wr, 3, ["Rule", "Minimum score shown", "Test cases where the rule applies",
                        "Hazard rate in those cases", "Times it raised the score"],
                rows, {4: PCT}, [44, 30, 18, 16, 16])

    order = ["Read Me", "Summary", "Risk Bands", "Calibration", "Risk Predictions", "Samples",
             "Passes", "Airports", "Stations", "Model Settings", "Safety Rules"]
    wb._sheets = [wb[n] for n in order]
    wb.save(OUT)
    print(f"[EXCEL] {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")
    print(f"[EXCEL] Samples: {len(data):,} rows × {len(cols)} columns; Risk Predictions: {n_pred:,} rows")


if __name__ == "__main__":
    main()
