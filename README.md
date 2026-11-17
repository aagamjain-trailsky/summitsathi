# SummitSathi

A portable weather-satellite receiver for trekkers, plus the study that tested its storm warnings on
real satellite data. This repository holds the complete project: all the code, from receiving a
satellite pass to the final Climb Risk Score, the processed data, the trained models, every result and
figure, and all the documents (IRIS submission and video, reviews, product requirements, decks,
reports and interview notes).

## What is in this repository

| Folder | What it holds |
| --- | --- |
| `archive/`, `pipeline/`, `simulator/`, `ui/`, `state/` | All the code (see the tree below) |
| `data/archive/archive.db` | SQLite database of every pass, station, image and location sample |
| `data/archive/truth/` | Airport weather reports (METAR) and ERA5 weather used as ground truth |
| `data/archive/crops/` | The 11,156 small image crops around each airport, one per sample |
| `data/archive/results/` | Trained models (`model_risk_v3.pkl` is the one the device uses), metrics, predictions, `samples.csv`, Excel workbooks, figures |
| `data/reference/` | Natural Earth coastlines and the land mask built from them |
| `logs/` | Logs from the full study run |
| `docs/submission/` | IRIS final paper, synopsis, submission PDF, final video and video script |
| `docs/reviews/` | IRIS reviewer feedback, rounds 1 and 2 |
| `docs/reports/` | Archive study, figures book, "How SummitSathi works" briefing |
| `docs/product/` | Product requirements (PRD), hardware requirements, flowcharts; older PRD versions |
| `docs/presentations/` | Pitch deck and IRIS video decks |
| `docs/data_workbooks/` | Excel workbooks with every data point (all years and the 2019 test) |
| `docs/interview_prep/` | Plain-language explanation of the model, likely questions, jargon sheet |

*Raw satellite images (separate download):* the 1,616 raw decoded satellite images (2.8 GB) are too large for GitHub. Download them from Google Drive: [SummitSathi_Raw_Satellite_Images.zip](https://drive.google.com/file/d/1LcjnPJDYV605TM2i2ud9f2ZIxPlJwF6h/view?usp=sharing). Unzip the file inside the repository folder; it unpacks into `data/archive/raw/`. Everything else runs without them. To rebuild them from scratch instead, run steps 1–3 of the pipeline below.

## Code layout

```
SummitSathi/
├── README.md                 this guide
├── requirements.txt          Python packages and the exact versions used
├── config.py                 shared settings (folders, satellites, default GPS position)
├── run_all.py                starts the live device software: simulator + alert engine + dashboard
│
├── pipeline/                 the alert logic that runs on the device
│   ├── alert_engine.py       main loop; uses v3, then v2, then v1, whichever applies
│   ├── alert_v3.py           final version: calibrated 0–100 Climb Risk Score, safety rules, No data / Stale
│   └── alert_v2.py           second version (kept for comparison)
│
├── simulator/                test inputs for the live software when no radio is connected
│   ├── satellite_sim.py      fake NOAA passes (for testing the software only, never used as data)
│   ├── gps_sim.py            fake GPS position
│   └── real_data_fetcher.py  fetches a real GOES image over the internet (demo only)
│
├── state/schema.py           the shared state file the services read and write
├── ui/                       the dashboard (Flask server + HTML page at http://127.0.0.1:5000)
│
├── archive/                  the research study on real archived satellite passes
│   ├── run_pipeline.sh       runs the whole study top to bottom (see below)
│   ├── db.py                 SQLite database layout
│   ├── collect.py            1  finds and downloads real NOAA passes from SatNOGS; screens noisy stations
│   ├── truth.py              2  airport weather reports (METAR) and ERA5 weather
│   ├── apt.py                3  decodes a real APT image: sync alignment, noise rejection, calibration, temperature
│   ├── geo.py                4  georeferencing: places every pixel on the map from the orbit
│   ├── landmask.py              coastline map used by the georeferencing check
│   ├── validate_geo.py       5  checks map position against real coastlines; measures the timing offset
│   ├── process.py            6  measures the 46 inputs around each airport for every pass
│   ├── evaluate.py           7  scores v1 and v2 (earlier versions) and builds the local-history baseline
│   ├── evaluate_v3.py        8  trains and tests the v3 hazard models (leave-one-year-out)
│   ├── risk_v3.py            9  trains and checks the Climb Risk Score; saves the model the device uses
│   ├── report.py             10 figures: map, case studies, feature importance, all-years charts
│   ├── report_iris.py           figures and results for the 2019 test year
│   ├── report_submission.py     flow charts, image anatomy, coastline check, equations
│   ├── export_excel.py       11 the Excel workbook with every data point and checkable formulas
│   ├── build_submission_pdf.py 12 the IRIS submission PDF
│   ├── summary_page.py          one-page HTML summary
│   └── README.md             method notes and limitations
│
└── data/reference/ne_50m_land.geojson   Natural Earth coastlines (public domain)
```

The trained models and results are included, so the live software shows the v3 Climb Risk Score
straight away. Rerunning the pipeline re-creates all of them in `data/archive/`.

## Setup (once)

```bash
cd SummitSathi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Needs Python 3.9 or newer, an internet connection for the download steps, and about 3.5 GB of free disk.

## A. Run the whole study, top to bottom

```bash
nohup sh archive/run_pipeline.sh > logs/pipeline.log 2>&1 &
tail -f logs/pipeline.log        # watch progress
```

`mkdir logs` first if the folder does not exist. Every step can be stopped and restarted; it carries
on where it left off.

| Step | What happens | Takes about |
| --- | --- | --- |
| 0 | Download airport weather reports for 44 airports, 2018–2025 | 1 hour |
| 1–2 | Find NOAA passes on SatNOGS, screen out stations that record only noise | 2–4 hours (SatNOGS limits requests) |
| 3 | Download the satellite images | 15 minutes |
| 4 | Check map position against coastlines; measure the timing offset | 10 minutes |
| 5 | Process every pass: calibrate, georeference, measure 46 inputs at each airport | 15 minutes |
| 6 | Download ERA5 weather for the months that have data | 10 minutes |
| 7 | Score v1 and v2 (earlier versions) | 2 minutes |
| 8 | Train and test v3 (leave-one-year-out) | 10 minutes |
| 9 | Train and check the Climb Risk Score | 5 minutes |
| 10 | Make all figures | 3 minutes |
| 11 | Make the Excel workbook | 2 minutes |
| 12 | Make the submission PDF | 1 minute |

To skip the slow SatNOGS search when the passes are already in the database:

```bash
SKIP_CRAWL=1 sh archive/run_pipeline.sh
```

**Optional: faster SatNOGS access.** A free SatNOGS account gives an API key. Save it, without
showing it on screen, to a private file that the crawler reads automatically:

```bash
read -s "TOKEN?Paste SatNOGS key: " && echo "$TOKEN" > .satnogs_token && chmod 600 .satnogs_token && unset TOKEN
```

The key is never printed or logged, and `.gitignore` keeps it out of version control.

### Where the outputs go

| Output | Location |
| --- | --- |
| Database of passes, stations, images and samples | `data/archive/archive.db` |
| Satellite images | `data/archive/raw/` |
| Airport reports and ERA5 | `data/archive/truth/` |
| All results (metrics, predictions, models) | `data/archive/results/` |
| Figures | `data/archive/results/figures/` |
| Excel workbook | `data/archive/results/SummitSathi_Archive_Data.xlsx` |
| Submission PDF | `~/Downloads/SummitSathi_IRIS_Submission.pdf` |

### Running single steps

Each step is a module and can be run on its own from the folder root, for example:

```bash
python -m archive.collect status          # how many passes are stored
python -m archive.process --all           # reprocess every pass
python -m archive.evaluate_v3             # retrain and retest v3
python -m archive.risk_v3                 # retrain the Climb Risk Score
```

## B. Run the live device software

```bash
python run_all.py
```

This starts the simulator, the alert engine and the dashboard at http://127.0.0.1:5000. With no
radio connected the simulator feeds test images, and the engine falls back to the original v1 logic,
because fake images carry no calibration. With a real decoded APT pass and its orbit data, and the
v3 model trained by step 9, the engine shows the calibrated Climb Risk Score.

## Main results (2019 test year, 2,860 cases the model never saw)

| Hazard | SummitSathi AUC | Local history AUC |
| --- | --- | --- |
| Thunderstorm | 0.90 | 0.81 |
| Rain within 3 hours | 0.88 | 0.68 |
| Rain now | 0.88 | 0.69 |
| Fog | 0.98 | 0.99 |

Climb Risk bands on 2019: a hazard followed 3% of the time at Minimal and 74% at Extreme.

## Data sources

- SatNOGS Network: archived NOAA APT images and orbit data (CC BY-SA 4.0)
- Iowa Environmental Mesonet: METAR airport reports
- Open-Meteo: ERA5 reanalysis (CC BY 4.0)
- Natural Earth: coastlines (public domain)

No personal data is stored. Observer and station names are dropped, and all sample locations are
public airports.
