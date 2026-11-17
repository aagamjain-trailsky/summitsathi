"""
Short product guide and interview briefing.

    python -m archive.build_interview_guide     # → ~/Downloads/SummitSathi_How_It_Works.pdf
"""
import json
from pathlib import Path
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Spacer, PageBreak, Table, TableStyle, KeepTogether

sys.path.insert(0, str(Path(__file__).parent.parent))
import archive.build_submission_pdf as bs
from archive.build_submission_pdf import P, bullets, table, figure, TEXT_W, MARGIN, PAGE_W, PAGE_H
from archive.build_submission_pdf import MUTED, RULE, PANEL, FIG

OUT = Path.home() / "Downloads" / "SummitSathi_How_It_Works.pdf"
DAY = json.loads((FIG / "prod_day_passes.json").read_text())


def panel(text):
    return Table([[P(text, "body")]], colWidths=[TEXT_W],
                 style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

def qa(q, a):
    return KeepTogether([P(f"<b>{q}</b>", "body"), P(a, "bullet")])


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 13 * mm, PAGE_W - MARGIN, PAGE_H - 13 * mm)
    canvas.setFont("Helvetica", 7.8); canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, PAGE_H - 11 * mm, "How SummitSathi works")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 11 * mm, "Briefing · Meteor-M edition")
    canvas.drawCentredString(PAGE_W / 2, 10 * mm, str(doc.page))
    canvas.restoreState()


def story():
    bs.fig_no[0] = 0
    bs.tab_no[0] = 0
    good = [p["peak"] for p in DAY if p["max_el"] >= 30]
    s = [P("How SummitSathi works", "title"),
         P("A short guide to the device, the hardware and the results", "subtitle"), Spacer(1, 6 * mm),
         panel("<b>In 30 seconds.</b> SummitSathi is a handheld device that gives trekkers weather warnings straight "
               "from space, with no phone signal or internet. A small antenna catches the cloud images that "
               "Meteor-M weather satellites broadcast as they pass overhead. A Raspberry Pi computer inside turns "
               "those images into a <b>Climb Risk Score from 0 to 100</b>, with simple advice such as \"avoid exposed "
               "ridges\". I tested the method on <b>11,156 real satellite observations over India</b> from 2018 to "
               "2025: it caught 7 in 10 thunderstorms and beat local weather records at spotting storms and rain.")]

    # ── 1 How it works ────────────────────────────────────────
    s += [P("1. How it works, in six steps", "h1")]
    steps = [
        ("Predict the pass.", "The GPS and clock tell the device where and when it is. Stored orbit data (TLE) and an "
         "orbit model (SGP4) predict when the next Meteor-M satellite will fly over, and the radio switches on two "
         "minutes before."),
        ("Catch the signal.", "For about 12 minutes the antenna picks up the satellite's broadcast at 137 MHz. An "
         "amplifier boosts the very weak signal, and the software radio turns it into digital samples, correcting for "
         "the Doppler shift as the satellite approaches and leaves."),
        ("Decode it.", "The signal is digital (LRPT). The computer recovers the bits, repairs errors with two "
         "error-correcting codes, unpacks the data and rebuilds three cloud images at about 1 km per pixel."),
        ("Turn pixels into physics.", "The infrared image becomes cloud-top temperature. Storm clouds are tall, so their "
         "tops are very cold: below −40 °C means deep storm cloud. The satellite's orbit places every pixel on the map."),
        ("Measure and predict.", "Around the trekker's GPS position the computer takes 46 measurements: how cold, how "
         "big and how close the clouds are, overshooting storm tops, fog at night, and whether clouds grew since the "
         "last pass. Trained models turn these into a Climb Risk Score. Safety rules keep the score at High if storm "
         "cloud is within 20 km."),
        ("Show the result.", "The screen shows the score, its band (Minimal to Extreme), advice, the reasons, and the "
         "time to the next pass. It says <i>Stale</i> if the last pass is over three hours old and <i>No data</i> if it "
         "has no view; it never says \"safe\" by default."),
    ]
    for i, (h, t) in enumerate(steps, 1):
        s.append(P(f"<b>{i}. {h}</b> {t}", "bullet"))
    s += [figure("prod_01b_system_hw.png",
                 "The parts of SummitSathi. The top row catches the signal; the Raspberry Pi runs every software step "
                 "offline; the dashed boxes support it; the orange boxes are what the trekker sees.")]

    # ── 2 Hardware ────────────────────────────────────────────
    s += [P("2. The hardware", "h1"),
          table([["Part", "Specification", "Its job"],
                 ["Computer", "Raspberry Pi 5, 4 GB RAM, quad-core Cortex-A76", "Runs decoding, maps, models and screen"],
                 ["Software radio", "RTL-SDR Blog V4 (RTL2832U + R828D), USB; RF-shielded compartment",
                  "Tunes to 137 MHz and digitises the signal"],
                 ["Antenna", "137 MHz V-dipole on a deployable rear mast", "Catches the satellite broadcast"],
                 ["Amplifier", "Low-noise amplifier (LNA) on the antenna feed", "Boosts the weak signal before noise is added"],
                 ["GPS", "u-blox NEO-M9N", "Trekker's position and precise time"],
                 ["Clock", "DS3231 real-time clock with coin cell", "Keeps time without GPS, for pass prediction"],
                 ["Storage", "128 GB industrial microSD + 32 GB for the system", "Offline maps, models, orbit data, images"],
                 ["Screen", "7-inch IPS touchscreen, 1024 × 600 or better, 800 nits, glove mode, toughened glass",
                  "Readable in full sun, usable with gloves"],
                 ["Battery", "4 × 18650 Li-ion cells, 12,000 mAh; USB-C 65 W charging (3–4 h); optional solar input",
                  "A full day of passes in the field"],
                 ["Case", "220 × 130 × 42 mm, ≤680 g, polycarbonate with rubber bumper, aluminium heat spine",
                  "Rugged, light, carries on a backpack strap"],
                 ["Controls and ports", "Glove-friendly buttons; USB-C, USB-A, microSD", "Use in cold weather; charging and updates"]],
                [0.17, 0.48, 0.35], "SummitSathi hardware, from the product requirements."),
          P("<b>Software.</b> Raspberry Pi OS Lite (64-bit) with a read-only system, so a sudden power cut cannot "
            "corrupt it. Every part runs as a service that restarts itself if it fails. Offline topographic maps "
            "(OpenTopoMap) and four screens: Home, Map, Satellite feed and Settings, plus a red night mode."),
          table([["Design target", "Value"],
                 ["Boot to usable screen", "≤ 60 seconds"],
                 ["Decode a pass / raise an alert", "≤ 3 minutes after the pass / ≤ 30 seconds after decoding"],
                 ["Battery life", "≥ 12 hours active, ≥ 48 hours standby"],
                 ["Toughness", "IP65 dust- and water-resistant; survives a 1.2 m drop onto concrete"],
                 ["Operating range", "−20 °C to +55 °C; up to 5,500 m altitude"]],
                [0.4, 0.6], "Design targets. These are what the device is built to achieve; they have not yet been field-tested."),
          P("The design also includes an L-band antenna for the American GOES satellites (1,694 MHz). They cannot be "
            "seen from India, so in India SummitSathi uses the 137 MHz Meteor-M signal.")]

    # ── 3 Satellites ──────────────────────────────────────────
    s += [P("3. The satellites", "h1"),
          P("SummitSathi listens to <b>Meteor-M N2-3 and N2-4</b>, Russian weather satellites launched in 2023 and 2024. "
            "They orbit about 830 km up, pole to pole, circling the Earth about 14 times a day, and broadcast their "
            "images free to anyone. Their camera (MSU-MR) sees six wavelengths, from visible light to thermal infrared, "
            "at about 1 km per pixel across a 2,800 km-wide strip. The older NOAA satellites used in the research study "
            "stopped broadcasting in 2025."),
          P(f"<b>How often:</b> on a typical day over Manali there are {len(DAY)} passes, of which {len(good)} are good "
            f"(around {', '.join(good)} IST). So SummitSathi gets a clear look at the sky roughly every 6 hours. Each pass "
            "lasts about 12 minutes.")]

    # ── 4 Results ─────────────────────────────────────────────
    s += [P("4. What the research showed", "h1"),
          P("I tested the method on real archived satellite images: 1,623 NOAA passes recorded by volunteer ground "
            "stations around India (2018–2025), matched with what 44 airports actually reported. The model trained on "
            "every year except 2019 and was then tested on 2019, which it had never seen."),
          table([["Result (2019 test, 2,860 cases)", "SummitSathi", "Local weather records"],
                 ["Thunderstorm detection (AUC)", "0.90", "0.81"],
                 ["Rain in the next 3 hours (AUC)", "0.88", "0.68"],
                 ["Thunderstorms caught (hiker-safety setting)", "70% (192 of 273)", "—"],
                 ["Hazard rate in the Minimal / Extreme bands", "3% / 74%", "—"]],
                [0.5, 0.25, 0.25], "Headline results. AUC: 0.5 is a coin toss, 1.0 is perfect."),
          P("<b>In plain words:</b> looking at the real clouds overhead predicts storms and rain better than knowing "
            "what the weather is usually like there in that season. The score is honest: when it says Extreme, a hazard "
            "followed 3 times in 4; when it says Minimal, almost never.")]

    # ── 5 Numbers ─────────────────────────────────────────────
    s += [KeepTogether([P("5. Key numbers to remember", "h1"),
          table([["Number", "What it is"],
                 ["137 MHz", "Frequency of the satellite broadcast"],
                 ["~830 km", "Height of the Meteor-M satellites"],
                 ["~12 minutes", "Length of one pass"],
                 ["~6 hours", "Time between good passes"],
                 ["~1 km", "Size of one pixel in a Meteor-M image"],
                 ["−40 °C", "Cloud tops colder than this mean storm cloud"],
                 ["46", "Measurements taken around the trekker"],
                 ["0–100", "Climb Risk Score range"],
                 ["11,156", "Real satellite observations used to test the method"],
                 ["0.90 vs 0.81", "Thunderstorm detection: SummitSathi vs local records"],
                 ["7 in 10", "Thunderstorms caught in testing"],
                 ["≥12 hours", "Battery life target"],
                 ["≤680 g", "Target weight"]],
                [0.3, 0.7], None)])]

    # ── 6 Q&A ─────────────────────────────────────────────────
    s += [P("6. Likely questions and short answers", "h1")]
    s += [qa("What is SummitSathi?", "A handheld device that gives trekkers weather warnings straight from weather "
             "satellites, without phone signal or internet."),
          qa("Why did you build it?", "Storms are one of the biggest dangers on high trails, and that is exactly where "
             "phones and weather apps stop working. The satellites are overhead anyway, so I built a way to use them directly."),
          qa("How does it get weather with no internet?", "Weather satellites broadcast their pictures openly by radio. "
             "SummitSathi's antenna and radio catch that broadcast, and a small computer inside turns it into a warning."),
          qa("Is it free and legal?", "Yes. The satellites broadcast to everyone at no cost, and SummitSathi only receives; "
             "it never transmits anything."),
          qa("How accurate is it?", "In testing on more than 11,000 real satellite observations over India, it caught 7 "
             "out of 10 thunderstorms and spotted storms and rain clearly better than local weather records."),
          qa("How is it different from a weather app or a satellite messenger?", "Apps need a connection. Satellite "
             "messengers send text forecasts. SummitSathi looks at the actual clouds above you, on the device itself."),
          qa("Who would use it?", "Trekkers, mountain guides, trekking companies, rescue teams and anyone heading where "
             "there is no signal."),
          qa("What was the hardest part?", "Real satellite data is messy. Many recordings were pure static, and my first "
             "version placed India 40% too wide on the map. I only found that by checking against real coastlines. My "
             "first set of alert rules caught none of the thunderstorms on real data, so I rebuilt the method."),
          qa("What are its limits?", "It sees the sky about every 6 hours, so a storm that forms in between can be "
             "missed. It needs a view of the sky. It helps you decide; it does not guarantee safety."),
          qa("What's next?", "Retraining the models on Meteor-M images, field-testing on Himalayan treks, and working "
             "with trekking companies and rescue teams.")]

    # ── 7 Be careful ──────────────────────────────────────────
    s += [P("7. Be careful to say it accurately", "h1")]
    s += bullets([
        "<b>\"0.90\" is not \"90% accurate\".</b> It is a ranking score (AUC). The simple version is: \"it caught 7 out "
        "of 10 thunderstorms in testing\".",
        "<b>The test used NOAA satellite data.</b> The device now uses Meteor-M, and the models are being retrained on "
        "Meteor-M images. Say \"the method was tested on real satellite data\", not \"the Meteor version is proven\".",
        "<b>The specifications are design targets.</b> Battery life, toughness and timings are what the device is built "
        "to achieve. Say so if it has not been field-tested yet.",
        "<b>It is a decision aid,</b> not a guarantee of safety.",
        "<b>GOES satellites do not cover India;</b> in India it uses Meteor-M."])
    return s


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=20 * mm,
                          bottomMargin=18 * mm, title="How SummitSathi works", subject="Product briefing")
    frame = Frame(MARGIN, 18 * mm, TEXT_W, PAGE_H - 38 * mm, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(story())
    print(OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    build()
