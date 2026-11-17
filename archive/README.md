# TrailSky archive study — real NOAA APT passes over India

Runs the TrailSky analysis on real, archived NOAA-15/18/19 APT passes and
scores it against observed weather.

## Pipeline

| Step | Command | What it does |
|---|---|---|
| — | `sh archive/run_pipeline.sh` | **Runs every step below, top to bottom (resumable)** |
| 1 | `python -m archive.collect crawl` | Finds NOAA APT observations from SatNOGS stations in 0–40°N, 55–100°E; screens each station and only crawls those producing real images |
| 2 | `python -m archive.collect download` | Downloads the decoded APT images (2080 px wide) |
| 3 | `python -m archive.truth metar 2018 2025` | Downloads airport METAR reports for 44 Indian airports |
| 4 | `python -m archive.validate_geo 20` | Checks georeferencing against Natural Earth coastlines |
| 5 | `python -m archive.process --all` | Calibrates, georeferences, crops each location, extracts features |
| 6 | `python -m archive.truth era5` | ERA5 reanalysis for the location-months that have samples |
| 7 | `python -m archive.evaluate` | Scores v1 / v2 / climatology (earlier versions) |
| 8 | `python -m archive.evaluate_v3` | Trains and tests the v3 hazard models (leave-one-year-out) |
| 9 | `python -m archive.risk_v3` | Trains and checks the Climb Risk Score; writes the model used by `pipeline/alert_v3.py` |

Outputs go to `data/archive/` (`archive.db`, `crops/`, `results/metrics.json`, `results/samples.csv`).

## Method

- **Line alignment**: Sync A (7 cycles of 1040 Hz) is found in every line by FFT cross-correlation.
- **Line quality**: a line is used only if sync correlation > 0.5 and the space-view strips are flat (IQR < 10). Speckle interference is removed with a 3×3 median filter.
- **Calibration**: each 128-line telemetry frame is calibrated with its own grey-scale wedges (1–8) and zero wedge (9). Wedge 16 identifies the AVHRR channel, so day/night channel switches are handled.
- **Brightness temperature (channel 4)**: two-point calibration between deep space and the internal black body (back-scan wedge 15), then inverse Planck at 925 cm⁻¹.
- **Station screening**: SatNOGS "good" status only means a signal was seen in the waterfall; many "good" APT images are pure noise. Each station's 6 highest passes are scored by column structure (real APT ≈ 5–50, noise ≈ 2) and noise-only stations are skipped.
- **Georeferencing**: the satellite position for each line (2 lines/s) comes from the pass TLE with SGP4 (pyorbital). The 909 pixels are **evenly spaced in ground distance** across the ±55.37° AVHRR swath (≈ ±1,500 km). The first version spaced them by scan angle, which made India ~40 % too wide; a coastline overlay on a real pass caught this.
- **Timing and orientation check** (`validate_geo.py`): clear daytime visible images are compared with Natural Earth coastlines after removing broad brightness trends. Orientation is confirmed not mirrored; the line-timing offset is measured per station (e.g. Pune ≈ 0 s, Bangalore ≈ +12 s from one clear pass) and applied in processing.
- **Night channel 3B**: the channel-ID wedge often decodes 3B as 3A; 3A (reflected sunlight) cannot be observed in darkness, so channel A over a dark scene is treated as 3B and calibrated at 2670 cm⁻¹.
- **Samples**: a 17×17 pixel box (≈56 km) around each airport, where the view angle is ≤ 50° and ≥ 70 % of the lines are clean.
- **Features**: cloud-top temperature statistics (min, p10, median, fractions below 273/253/233/220 K); **storm distance** — distance from the airport to the nearest < 233 K pixel anywhere in the pass, and cold-pixel counts within 50/150 km; **night fog** — BT(ch4) − BT(ch3B), positive over fog and low stratus; local hour, month and view angle.
- **Models**: v1 = original thresholds, unchanged. v2 = tuned temperature thresholds and an L2 logistic regression (`evaluate.py`). **v3 (final)** = gradient-boosted trees on 46 inputs, one per hazard (`evaluate_v3.py`), plus a calibrated 0–100 Climb Risk Score with safety rules (`risk_v3.py`).
- **Ground truth**: METAR reports within ±1 h (rain, thunderstorm/CB, fog, cloud oktas), METAR in the next 3 h for the forecast target, and ERA5 cloud cover and precipitation.
- **Fair test (v3)**: leave-one-year-out. 2020 tunes settings, thresholds and calibration; each other year is predicted by a model trained without it. The submission reports the 2019 test year (trained on 5,808 cases from 2020–2025, tested on 2,860). F1 has 95 % bootstrap confidence intervals.

## Known limitations (state these in the write-up)

- **Black-body temperature is assumed at 290 K** rather than read from the PRT wedges, so absolute temperatures can be off by a few K. Thresholds learned from data absorb this.
- **Line timing assumes the image starts at the SatNOGS observation start time.** `validate_geo.py` measures the real offset.
- **METAR is a point observation at an airport**, while the satellite box is ~65 km wide. Mountain trek sites are represented by the nearest airport (e.g. Leh, Kullu, Shimla).
- **ERA5 is a model reanalysis (~25 km)**, not an observation. It's used for cloud cover only, as a cross-check.
- **SatNOGS images vary in quality**, and noisy passes are rejected. The yield is reported.
- **Fog**: the 11 µm channel alone cannot see fog; the 3B fog test only works at night.
- **Mountain airports** (Leh, Thoise, Srinagar, Pakyong) have only ~2 years of METAR, so mountain-specific results have wide error bars.
- **Timing offset** is measured from few clear passes for some stations; a sensitivity check (re-scoring with ±12 s) is a recommended follow-up.
- **Data use**: SatNOGS data is CC BY-SA. Observer usernames and station names are not stored; station positions are rounded.
