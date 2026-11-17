#!/bin/sh
# Full TrailSky archive study, top to bottom. Every step is resumable.
#   nohup sh archive/run_pipeline.sh > logs/pipeline.log 2>&1 &
#   SKIP_CRAWL=1 sh archive/run_pipeline.sh   # use only passes already found
cd "$(dirname "$0")/.." || exit 1
PY=venv/bin/python
step() { echo; echo "==== $(date '+%H:%M:%S') $1 ===="; }

if [ "$SKIP_CRAWL" = "1" ]; then
    step "1-2/12 Crawl skipped (SKIP_CRAWL=1)"
else
    step "0/12 Airport weather reports (METAR, 2018-2025)"
    $PY -u -m archive.truth metar 2018 2025 || exit 1

    step "1/12 Waiting for any running crawl"
    while pgrep -f "m archive.collect crawl" >/dev/null; do sleep 60; done

    step "2/12 Crawl (finishes anything left)"
    $PY -u -m archive.collect crawl || exit 1
fi

step "3/12 Download images"
$PY -u -m archive.collect download || exit 1

step "4/12 Measure georeferencing timing per station"
$PY -u -m archive.validate_geo 60 || exit 1

step "5/12 Process every pass (fresh, with measured offsets)"
$PY -u -m archive.process --all || exit 1

step "6/12 ERA5 for sampled location-months"
$PY -u -m archive.truth era5 || exit 1

step "7/12 Evaluate v1 / v2 (earlier versions, for comparison)"
$PY -u -m archive.evaluate || exit 1

step "8/12 Train and test v3 hazard models (leave-one-year-out)"
$PY -u -m archive.evaluate_v3 || exit 1

step "9/12 Train and check the Climb Risk Score"
$PY -u -m archive.risk_v3 || exit 1

step "10/12 Figures"
$PY -u -m archive.report || exit 1
$PY -u -m archive.report_iris || exit 1
$PY -u -m archive.report_submission || exit 1

step "11/12 Excel workbook"
$PY -u -m archive.export_excel || exit 1

step "12/12 Submission PDF"
$PY -u -m archive.build_submission_pdf || exit 1

step "Done"
$PY -m archive.collect status
