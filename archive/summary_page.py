"""Builds the one-page results summary (HTML) from the results files."""
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from archive.evaluate import RESULTS_DIR

FIG = RESULTS_DIR / "figures"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS_DIR / "summary.html"

m = json.loads((RESULTS_DIR / "metrics_v3.json").read_text())
risk = json.loads((RESULTS_DIR / "risk_v3.json").read_text())
cases = json.loads((FIG / "cases.json").read_text())
geo_val = json.loads((RESULTS_DIR / "geo_validation.json").read_text())["summary"]

def img(name, alt):
    data = base64.b64encode((FIG / name).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{alt}">'

def pct(x):
    return f"{100 * x:.0f}%"

ev = m["events"]
th, r3, rn, fg = ev["thunder_now"], ev["rain_next3h"], ev["rain_now"], ev["fog_now"]
NAMES = {"thunder_now": "Thunderstorm", "rain_next3h": "Rain within 3 hours",
         "rain_now": "Rain (now)", "fog_now": "Fog"}

rows_v3 = "".join(
    f"<tr><td>{NAMES[k]}</td><td class='n'>{e['test_events']:,}</td>"
    f"<td class='n'><strong>{e['auc']:.2f}</strong></td><td class='n'>{e['satellite_only_auc']:.2f}</td>"
    f"<td class='n'>{e['climatology_auc']:.2f}</td>"
    f"<td class='n'>{pct(e['safety']['recall'])}</td><td class='n'>{pct(e['safety']['precision'])}</td></tr>"
    for k, e in ((k, ev[k]) for k in ("thunder_now", "rain_next3h", "rain_now", "fog_now")))

rows_bands = "".join(
    f"<tr><td>{b['band'].title()}</td><td class='n'>{b['score_range']}</td>"
    f"<td class='n'>{b['share_of_cases_pct']:.0f}%</td>"
    f"<td class='n'><strong>{b['observed_hazard_rate_pct']:.0f}%</strong></td><td>{b['decision']}</td></tr>"
    for b in risk["bands"] if b["n"])

sr = risk["safety_rules"]
c1, c2 = cases[0], cases[1] if len(cases) > 1 else None
top_th = [k for k, _ in th["top_features"][:6]]

html = f"""<title>TrailSky Archive Study</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Source+Sans+3:wght@400;600&display=swap">
<style>
/* Layout: single column report, 46rem measure; figures may span a wider 64rem band */
:root {{
  --paper: #FFFFFF; --ink: #333333; --muted: #5E6369; --rule: #D9DCE0;
  --navy: #0A2540; --navy-2: #1A3A5C; --accent: #E85D26; --panel: #F5F5F5;
  --serif: "Source Serif 4", Georgia, "Times New Roman", serif;
  --sans: "Source Sans 3", "Helvetica Neue", Arial, sans-serif;
  color-scheme: light;
}}
body {{ background: var(--paper); color: var(--ink); font: 16px/1.6 var(--serif);
  padding-inline: 20px; padding-block: 40px 64px; }}
.page {{ max-width: 64rem; margin: 0 auto; display: grid; gap: 40px; }}
.measure {{ max-width: 46rem; }}
header {{ border-bottom: 2px solid var(--navy); padding-bottom: 20px; display: grid; gap: 8px; }}
.kicker {{ font: 600 12px/1.3 var(--sans); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }}
h1 {{ font: 700 2.1rem/1.15 var(--serif); color: var(--navy); margin: 0; text-wrap: balance; }}
h2 {{ font: 700 1.35rem/1.25 var(--serif); color: var(--navy); margin: 0 0 12px; text-wrap: balance; }}
h3 {{ font: 600 1.05rem/1.3 var(--serif); color: var(--navy); margin: 0 0 6px; }}
p {{ margin: 0 0 12px; }}
.abstract {{ font-size: 1.08rem; }}
section {{ display: grid; gap: 4px; }}
.headline {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: 0;
  border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }}
.stat {{ padding: 16px 16px 16px 0; display: grid; gap: 2px; }}
.stat + .stat {{ border-left: 1px solid var(--rule); padding-left: 16px; }}
.stat .v {{ font: 700 2rem/1.1 var(--serif); color: var(--navy); font-variant-numeric: tabular-nums; }}
.stat .v.hl {{ color: var(--accent); }}
.stat .l {{ font: 400 14px/1.4 var(--sans); color: var(--muted); }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font: 15px/1.4 var(--sans); }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font-weight: 600; color: var(--navy); border-bottom: 2px solid var(--navy); white-space: nowrap; }}
td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.caption {{ font: 14px/1.45 var(--sans); color: var(--muted); margin-top: 6px; }}
figure {{ margin: 0; display: grid; gap: 6px; }}
figure img {{ border: 1px solid var(--rule); background: #fff; width: 100%; height: auto; }}
.fig-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 24px; align-items: start; }}
ol, ul {{ margin: 0 0 12px; padding-left: 1.3em; display: grid; gap: 6px; }}
.method li strong {{ color: var(--navy); }}
.note {{ background: var(--panel); padding: 14px 16px; font: 15px/1.5 var(--sans); }}
code {{ font: 14px/1.4 ui-monospace, Menlo, Consolas, monospace; }}
footer {{ border-top: 1px solid var(--rule); padding-top: 16px; font: 14px/1.5 var(--sans); color: var(--muted); }}
@media (max-width: 40rem) {{ h1 {{ font-size: 1.6rem; }} .stat + .stat {{ border-left: 0; padding-left: 0; border-top: 1px solid var(--rule); }} }}
</style>

<main class="page">
<header>
  <div class="kicker">Student research project · Weather-satellite hazard warnings for trekkers in India</div>
  <h1>Can a portable weather-satellite receiver warn trekkers of storms?</h1>
  <p class="measure abstract">We ran the TrailSky alert system on <strong>{m['n_samples']:,} real satellite–weather matches</strong>:
  archived NOAA-15/18/19 APT images received by ground stations in India (2018–2025), each compared with what
  the nearest airport actually reported. Every result below comes from years the model never saw during training.</p>
</header>

<section>
  <div class="headline">
    <div class="stat"><span class="v">{th['test_n']:,}</span><span class="l">out-of-year test predictions at 44 airports</span></div>
    <div class="stat"><span class="v hl">{th['auc']:.2f}</span><span class="l">thunderstorm detection (AUC), against {th['climatology_auc']:.2f} for the airport's own climate history</span></div>
    <div class="stat"><span class="v">{pct(th['safety']['recall'])}</span><span class="l">of thunderstorms caught at the hiker-safety setting; {pct(th['safety']['precision'])} of those alerts were right</span></div>
    <div class="stat"><span class="v">{risk['bands'][0]['observed_hazard_rate_pct']:.0f}% → {risk['bands'][-1]['observed_hazard_rate_pct']:.0f}%</span><span class="l">hazard rate from the lowest to the highest Climb Risk band</span></div>
  </div>
</section>

<section class="measure">
  <h2>Question</h2>
  <p>TrailSky receives weather-satellite images on a portable radio and turns them into storm alerts for people on
  mountain trails. The original version was tuned on simulated images. Does it work on real satellite data, and
  does the satellite tell a trekker anything beyond the usual weather for that place and season?</p>
</section>

<section class="measure method">
  <h2>Method</h2>
  <ol>
    <li><strong>Real images.</strong> 24 SatNOGS volunteer ground stations around India were searched; 14 recorded
      real images and the rest recorded only noise and were skipped automatically. From their 1,425 archived APT
      passes, 677 were clean enough to use, giving {m['n_samples']:,} location samples from 13 stations.</li>
    <li><strong>Calibration.</strong> Each image line was aligned on its sync pulse, noisy lines removed, and the
      telemetry wedges used to convert pixels to cloud-top temperature (11 µm) and, at night, the 3.7 µm fog channel.</li>
    <li><strong>Georeferencing.</strong> Each pixel was placed using the satellite's orbit (TLE) and checked against
      real coastlines. This check found two errors that were then fixed: pixel spacing (India appeared 40% too wide)
      and an {geo_val['median_offset_s']:.0f}-second timing offset ({geo_val['strong_matches']} clear coastline matches).</li>
    <li><strong>Features.</strong> Around each of 44 airports: cloud-top temperature, storm structure
      (coldest top within 50/100 km, overshooting tops, distance to the nearest storm cloud), visible brightness by day,
      a night fog signal, and cloud-top cooling between back-to-back passes.</li>
    <li><strong>Ground truth.</strong> Airport METAR reports within one hour of the pass (thunderstorm, rain, fog)
      and over the following three hours.</li>
    <li><strong>Model and fair test.</strong> Gradient-boosted trees, tuned on 2020 only. Every other year was then
      predicted by a model trained without that year (leave-one-year-out). The baseline is the airport's own
      climate history for that month and time of day, also built without the test year.</li>
  </ol>
</section>

<section>
  <h2 class="measure">Results: hazard detection (v3)</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Hazard</th><th class="n">Cases</th><th class="n">v3 AUC</th><th class="n">Satellite only</th>
      <th class="n">Climate history only</th><th class="n">Caught (safety)</th><th class="n">Alerts correct</th></tr></thead>
    <tbody>{rows_v3}</tbody>
  </table></div>
  <p class="caption">AUC: 0.5 is a coin toss and 1.0 is perfect. "Caught" and "Alerts correct" use the hiker-safety
  alert setting, which is tuned to miss as few hazards as possible, so it accepts more false alarms.</p>
  <figure>{img('1_roc_v3_vs_history.png', 'Detection curves for v3 against climate history for four hazards')}
    <figcaption class="caption">Each curve shows how many real events are caught (up) against how many false alarms
    are raised (right). A curve closer to the top-left corner is better. The dashed line is the airport's climate history.</figcaption></figure>
</section>

<section class="fig-row">
  <figure>{img('2_safety_tradeoff_thunder.png', 'Thunderstorm alert trade-off between storms caught and alerts correct')}
    <figcaption class="caption">Catching more storms means more false alarms. The orange point is the hiker-safety setting.</figcaption></figure>
  <figure>{img('3_feature_importance_thunder_now.png', 'Inputs the thunderstorm model relies on most')}
    <figcaption class="caption">After the airport's own storm history, the model relies on storm structure:
    overshooting tops, the coldest cloud top, and how much deep storm cloud is nearby.</figcaption></figure>
</section>

<section>
  <h2 class="measure">Results: Climb Risk Score (0–100)</h2>
  <p class="measure">The score is the calibrated chance, out of 100, that a thunderstorm, rain within three hours,
  or fog is reported at the location. It was checked on {risk['test_n']:,} predictions from unseen years.
  AUC {risk['auc']:.2f}; prediction error {pct(risk['brier_skill_vs_climatology'])} lower than using climate history alone
  (Brier score {risk['brier']:.3f} against {risk['brier_climatology']:.3f}).</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Band</th><th class="n">Score</th><th class="n">Share of cases</th>
      <th class="n">Hazard reported</th><th>Advice shown</th></tr></thead>
    <tbody>{rows_bands}</tbody>
  </table></div>
  <div class="fig-row" style="margin-top:16px">
    <figure>{img('6_risk_score_calibration.png', 'Calibration of the Climb Risk Score')}
      <figcaption class="caption">If the score is honest, points lie on the dashed line. Scores of 90–100 came true
      84% of the time, so no score should be read as certainty.</figcaption></figure>
    <figure>{img('7_risk_bands.png', 'Observed hazard rate in each Climb Risk band')}
      <figcaption class="caption">Each band is riskier than the one below it.</figcaption></figure>
  </div>
  <p class="measure" style="margin-top:12px"><strong>Safety rules.</strong> The score is never shown below High when
  storm cloud colder than −40 °C is within 20 km (a hazard followed in {sr['storm_within_20km']['test_hazard_rate_pct']:.0f}%
  of {sr['storm_within_20km']['test_n']} test cases) or an overshooting top is within 50 km
  ({sr['overshooting_top_within_50km']['test_hazard_rate_pct']:.0f}% of {sr['overshooting_top_within_50km']['test_n']}).
  Without a usable satellite view the system shows <em>No data</em>, never <em>Safe</em>; a pass more than
  {risk['stale_after_hours']:.0f} hours old is marked <em>Stale</em>.</p>
</section>

<section>
  <h2 class="measure">Case studies from real passes</h2>
  <div class="fig-row">
    <figure>{img(next(f.name for f in FIG.glob('5_case_1_*.png')), 'Thunderstorm caught at ' + c1['location'])}
      <figcaption class="caption"><strong>Caught.</strong> {c1['location']}, {c1['time_utc']} UTC ({c1['satellite']}).
      Storm cloud {c1['storm_dist_km']:.0f} km away with tops at {c1['coldest_100km_c']} °C. Climb Risk
      {c1['risk_score']}/100 ({c1['risk_band'].title()}). The airport reported a thunderstorm and rain.</figcaption></figure>
    {"" if not c2 else f'''<figure>{img(next(f.name for f in FIG.glob('5_case_2_*.png')), 'Thunderstorm missed at ' + c2['location'])}
      <figcaption class="caption"><strong>Missed.</strong> {c2['location']}, {c2['time_utc']} UTC ({c2['satellite']}).
      The nearest storm cloud in the pass was {c2['storm_dist_km']:.0f} km away, so the score was
      {c2['risk_score']}/100 ({c2['risk_band'].title()}). A thunderstorm was still reported, probably because a storm grew
      between satellite passes.</figcaption></figure>'''}
  </div>
</section>

<section class="fig-row">
  <figure>{img('4_map_of_samples.png', 'Map of the 44 airports and number of matches at each')}</figure>
  <div class="measure">
    <h2>Limitations</h2>
    <ul>
      <li>Clean images are concentrated in 2019–2021. Results for 2022–25 are weaker (thunderstorm AUC
        {th['folds'][-1]['auc']:.2f} on {th['folds'][-1]['n']} cases) because those archived images are noisier.</li>
      <li>Ground truth comes from airports. A trail can be tens of kilometres from the nearest airport, and
        mountain airports (Leh, Srinagar, Shimla) have fewer reports.</li>
      <li>Rain alerts raise many false alarms, because rain at any given moment is rare (3–4% of cases).</li>
      <li>Fog is predicted almost entirely from climate history; the satellite adds little.</li>
      <li>One pass every few hours cannot see storms that form between passes, as in the Kochi case.</li>
      <li>Cloud-top temperatures assume a nominal on-board calibration target temperature and may be off by a few kelvin.</li>
    </ul>
    <div class="note">The system improves on climate history alone, but it does not guarantee safety. It is
    meant to support a trekker's judgement, not replace it.</div>
  </div>
</section>

<footer class="measure">Data: SatNOGS Network (CC BY-SA), Iowa Environmental Mesonet METAR archive, ERA5 via Open-Meteo,
Natural Earth. Code and full results: <code>trailsky/archive/</code> — <code>metrics_v3.json</code>,
<code>risk_v3.json</code>, <code>samples.csv</code>. All configurations tried are recorded in the results files.</footer>
</main>
"""
OUT.write_text(html)
print(f"[SUMMARY] {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
