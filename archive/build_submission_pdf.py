"""
Builds the IRIS submission PDF with figures placed in their sections.

    python -m archive.build_submission_pdf      # → ~/Downloads/TrailSky_IRIS_Submission.pdf
"""
from pathlib import Path
import sys

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Image, Table,
                                TableStyle, KeepTogether, PageBreak, Flowable, NextPageTemplate)

sys.path.insert(0, str(Path(__file__).parent.parent))
FIG = Path(__file__).parent.parent / "data" / "archive" / "results" / "figures"
OUT = Path.home() / "Downloads" / "TrailSky_IRIS_Submission.pdf"

NAVY, INK, MUTED, RULE = HexColor("#0A2540"), HexColor("#333333"), HexColor("#5E6369"), HexColor("#D9DCE0")
ORANGE, PANEL = HexColor("#E85D26"), HexColor("#F5F5F5")
PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
TEXT_W = PAGE_W - 2 * MARGIN

S = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=26, leading=31, textColor=NAVY),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=13, leading=18, textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=NAVY,
                         spaceBefore=14, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=NAVY,
                         spaceBefore=9, spaceAfter=3, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=11, leading=15.2, textColor=INK, spaceAfter=6),
    "lead": ParagraphStyle("lead", fontName="Times-Bold", fontSize=11, leading=15.2, textColor=INK, spaceAfter=6),
    "bullet": ParagraphStyle("bullet", fontName="Times-Roman", fontSize=11, leading=15, textColor=INK,
                             leftIndent=12, bulletIndent=2, spaceAfter=3),
    "caption": ParagraphStyle("caption", fontName="Helvetica", fontSize=8.8, leading=12, textColor=MUTED,
                              spaceBefore=3, spaceAfter=10),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.6, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.6, leading=11, textColor=white),
    "abstract": ParagraphStyle("abstract", fontName="Times-Roman", fontSize=11, leading=15.5, textColor=INK,
                               spaceAfter=6, leftIndent=8, rightIndent=8),
    "ph": ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=ORANGE,
                         alignment=TA_CENTER),
    "phs": ParagraphStyle("phs", fontName="Helvetica", fontSize=8.5, leading=12, textColor=MUTED,
                          alignment=TA_CENTER),
}
fig_no = [0]
tab_no = [0]


def P(text, style="body"):
    return Paragraph(text, S[style])

def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="•") for t in items]

def figure(fname, caption, width=TEXT_W):
    fig_no[0] += 1
    w, h = PILImage.open(FIG / fname).size
    width = min(width, TEXT_W)
    height = width * h / w
    if height > 175 * mm:
        height = 175 * mm
        width = height * w / h
    return KeepTogether([Image(str(FIG / fname), width=width, height=height),
                         P(f"<b>Figure {fig_no[0]}.</b> {caption}", "caption")])

def equation(fname, number, height=None):
    """Equations are rendered at one font size, so they are placed at their natural size."""
    w, h = PILImage.open(FIG / fname).size
    img = Image(str(FIG / fname), width=w / 300 * 72, height=h / 300 * 72)
    t = Table([[img, P(f"({number})", "body")]], colWidths=[TEXT_W - 15 * mm, 15 * mm])
    t.setStyle(TableStyle([("ALIGN", (0, 0), (0, 0), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t

def table(rows, widths, caption=None, bold_last=0):
    tab_no[0] += 1
    data = [[Paragraph(str(c), S["cellb"]) for c in rows[0]]] + \
           [[Paragraph(str(c), S["cell"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=[w * TEXT_W for w in widths], repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LEFTPADDING", (0, 0), (-1, -1), 4),
             ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    for i in range(bold_last):
        style.append(("BACKGROUND", (0, len(rows) - 1 - i), (-1, len(rows) - 1 - i), PANEL))
    t.setStyle(TableStyle(style))
    out = [t]
    if caption:
        out.append(P(f"<b>Table {tab_no[0]}.</b> {caption}", "caption"))
    return KeepTogether(out)


class Placeholder(Flowable):
    """Dashed box marking where a photo of the device goes."""
    def __init__(self, title, note, height=60 * mm, width=TEXT_W):
        super().__init__()
        self.title, self.note, self.h, self.w = title, note, height, width
    def wrap(self, *_):
        return self.w, self.h + 8
    def draw(self):
        c = self.canv
        c.setStrokeColor(ORANGE); c.setDash(4, 3); c.setLineWidth(1)
        c.roundRect(0, 4, self.w, self.h, 6, stroke=1, fill=0)
        c.setDash()
        c.setFillColor(ORANGE); c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(self.w / 2, 4 + self.h / 2 + 6, f"[ INSERT PHOTO: {self.title} ]")
        c.setFillColor(MUTED); c.setFont("Helvetica", 8.5)
        c.drawCentredString(self.w / 2, 4 + self.h / 2 - 10, self.note)


def on_page(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 13 * mm, PAGE_W - MARGIN, PAGE_H - 13 * mm)
    canvas.setFont("Helvetica", 7.8); canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, PAGE_H - 11 * mm, "TrailSky: satellite storm warnings for trekkers")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 11 * mm, "IRIS National Fair submission")
    canvas.drawCentredString(PAGE_W / 2, 10 * mm, str(doc.page))
    canvas.restoreState()


def story():
    s = []
    # ── Title page ────────────────────────────────────────────
    s += [Spacer(1, 28 * mm), P("TrailSky", "title"), Spacer(1, 3 * mm),
          P("Can a portable weather-satellite receiver warn trekkers of storms? "
            "A test on 11,156 real satellite–weather matches over India", "subtitle"),
          Spacer(1, 8 * mm),
          P("[Student name] · [School] · IRIS National Fair · [Category]", "meta"),
          P("October 2026", "meta"), Spacer(1, 12 * mm),
          Placeholder("TrailSky device, front view", "Hero photo of the handheld receiver, screen on", 85 * mm),
          Spacer(1, 6 * mm)]
    s += [Table([[P("<b>Key results on a test year the model never saw (2019, 2,860 cases)</b><br/>"
                    "Thunderstorm detection AUC <b>0.90</b>, against 0.81 for local weather history · "
                    "<b>70%</b> of thunderstorms caught at the hiker-safety setting · Climb Risk bands from "
                    "<b>3%</b> (Minimal) to <b>74%</b> (Extreme) hazard rate", "body")]],
                colWidths=[TEXT_W],
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))]
    s.append(PageBreak())

    # ── 1 Abstract ────────────────────────────────────────────
    s += [P("1. Abstract", "h1"),
          P("Trekkers in the Himalaya and the Western Ghats are often caught by storms where there is no phone "
            "signal and no weather station. TrailSky is a handheld receiver that picks up images directly from "
            "polar-orbiting weather satellites and turns them into a 0–100 Climb Risk Score. Its first version "
            "was tuned on simulated images. This project asks whether it works on real data, and whether the "
            "satellite adds anything to what a trekker could know from the usual weather for that place and "
            "season.", "abstract"),
          P("We processed 1,425 real archived passes of NOAA-15, 18 and 19, recorded by volunteer ground "
            "stations around India between 2018 and 2025. Each usable image was calibrated to cloud-top "
            "temperature, placed on the map, checked against real coastlines, and measured around 44 Indian "
            "airports. This produced 11,156 satellite–weather matches, each compared with what the airport "
            "actually reported. Gradient-boosted tree models were trained on every year except 2019 and then "
            "tested once on 2019.", "abstract"),
          P("On the 2,860 test cases, TrailSky detected thunderstorms with an AUC of 0.90 against 0.81 for local "
            "history, and rain within three hours with 0.88 against 0.68. At its hiker-safety setting it caught "
            "70% of thunderstorms. Its Climb Risk Score proved honest: a hazard followed in 3% of Minimal cases "
            "and 74% of Extreme cases. The satellite adds real information for storms and rain; fog is predicted "
            "mainly by local history, and storms that form between passes remain the main weakness.", "abstract")]

    # ── 2 Introduction ────────────────────────────────────────
    s += [P("2. Introduction", "h1"),
          P("Weather is one of the main dangers on a high trail. Thunderstorms in the monsoon and pre-monsoon "
            "months can grow from clear sky to lightning within a few hours, and on an exposed ridge lightning, "
            "heavy rain and sudden fog are all serious hazards. The tools most trekkers rely on fail exactly "
            "where they are needed: weather apps need mobile data, and the ground weather stations that feed "
            "forecasts are sparse in the mountains. In our own data, the mountain airports at Leh, Srinagar and "
            "Shimla had far fewer weather reports than the cities."),
          P("Weather satellites, however, pass overhead several times a day and broadcast their images openly on "
            "137 MHz. A small antenna and radio can receive them anywhere with a view of the sky, with no "
            "subscription and no signal. TrailSky is built on that idea."),
          P("Research question", "h2"),
          P("Can cloud images received directly from a weather satellite warn a trekker of a thunderstorm, rain or "
            "fog better than knowing the usual weather for that place, month and time of day?"),
          P("Hypothesis", "h2"),
          P("Cloud-top temperature and storm structure measured from the satellite image will rank real hazards "
            "above calm moments more often than the local weather history alone (a higher AUC on a year the model "
            "never saw)."),
          P("Contribution", "h2")]
    s += bullets([
        "A complete processing chain for real APT satellite images, from noisy radio recording to calibrated, "
        "mapped cloud-top temperature, validated against real coastlines.",
        "A dataset of 11,156 satellite–weather matches over India, built from public archives.",
        "A tested hazard model and a calibrated 0–100 Climb Risk Score with safety rules, evaluated on a held-out year.",
        "An honest account of what failed: the original thresholds caught none of 37 thunderstorms on real data."])

    # ── 3 The device ──────────────────────────────────────────
    s += [P("3. The TrailSky device", "h1"),
          P("TrailSky is a handheld unit with four main parts: a 137 MHz antenna, a software-defined radio "
            "receiver, a small on-board computer, and a GPS receiver with a screen. The whole algorithm described "
            "in this report runs on the device itself. It needs no internet; orbit data for predicting passes is "
            "refreshed whenever a connection is available, for example at the trailhead."),
          table([["Device part", "What it does", "Algorithm stage it serves (Figure 1)"],
                 ["137 MHz antenna", "Picks up the satellite's APT broadcast during a 10–15 minute pass",
                  "1 Receive"],
                 ["Software-defined radio", "Tunes to the satellite and records the audio signal", "1 Receive"],
                 ["On-board computer", "Decodes, cleans, calibrates, maps and scores each pass",
                  "1–4, all processing"],
                 ["GPS receiver and clock", "Gives the trekker's position and accurate time for pass prediction",
                  "1 Pass prediction, 3 Measure"],
                 ["Screen", "Shows the Climb Risk Score, band, advice and reasons", "4 Decide"],
                 ["Battery", "Powers a full day of passes in the field", "All"]],
                [0.22, 0.48, 0.30], "How each part of the device maps to the algorithm."),
          Placeholder("Inside the device", "Labelled photo of the antenna, radio, computer, GPS and battery", 70 * mm),
          Placeholder("Climb Risk Score screen", "Screen showing score, band, advice and reasons", 70 * mm)]

    # ── 4 How TrailSky works ──────────────────────────────────
    s += [P("4. How TrailSky works", "h1"),
          P("Every pass goes through the same chain of sixteen steps in four stages (Figure 1). Stage 1 predicts "
            "when the next satellite will pass, records its signal and turns the audio into image lines. Stage 2 "
            "cleans those lines and converts brightness into a physical quantity, the temperature of the cloud "
            "tops. Stage 3 places every pixel on the map and measures 46 properties of the clouds around the "
            "trekker. Stage 4 turns those measurements into hazard probabilities, a calibrated Climb Risk Score "
            "and a short piece of advice."),
          figure("sub_01_algorithm.png",
                 "The TrailSky algorithm. Each row is one stage; arrows show the order of processing. The dashed boxes "
                 "at the bottom are extra inputs: the airport's long-term weather history, the previous satellite "
                 "pass (used to measure whether clouds are growing), and the real data the models were trained on. "
                 "The orange box is what the trekker sees. A pass is processed from recording to warning in the "
                 "field, without internet."),
          P("Two design choices make the output trustworthy. First, every stage was checked against real data "
            "before it was trusted: the map position against real coastlines, the temperatures against physical "
            "limits, and the predictions against airport reports. Second, the device never says \"safe\" by "
            "default. If it has no usable view of the trekker's position it shows <i>No data</i>, and if the "
            "latest pass is more than three hours old it marks the result <i>Stale</i>.")]

    # ── 5 Data ────────────────────────────────────────────────
    s += [P("5. Data", "h1"),
          P("All data came from public archives. Satellite images came from the SatNOGS network, where volunteers "
            "around the world record satellite passes and publish them. Ground truth came from METAR reports, the "
            "standard weather observations that airports issue every 30 to 60 minutes, from 44 Indian airports "
            "chosen to cover mountains, hills, coasts and plains."),
          figure("iris_4_data_funnel.png",
                 "From passes found to passes used. Of 1,623 passes found, 191 came from two stations that recorded "
                 "only radio static and were rejected automatically. Of the remaining 1,425, 677 were clean enough to "
                 "calibrate, and 625 had at least one airport inside their clean section. Most of the loss is due to "
                 "noisy recordings, not to the method.", 0.85 * TEXT_W),
          P("One pass produces many data points, because a single NOAA image covers a strip about 3,000 km wide, "
            "nearly the whole width of India. Each airport inside the clean part of a pass gives one data point. "
            "The 625 usable passes covered on average 18 airports each; one pass on 27 January 2019 covered 40. "
            "Table 2 consolidates the dataset by year."),
          table([["Year", "Role", "Passes found", "Clean passes", "Data points", "With airport report",
                  "Thunder-storms", "Rain within 3 h", "Fog"],
                 ["2019", "<b>Test</b>", "338", "193", "3,833", "2,860", "273", "114", "22"],
                 ["2020", "Training (tuning)", "222", "92", "1,036", "880", "50", "59", "6"],
                 ["2021", "Training", "539", "325", "5,758", "4,559", "269", "104", "156"],
                 ["2022", "Training", "152", "4", "12", "7", "0", "0", "0"],
                 ["2023", "Training", "72", "10", "142", "88", "16", "13", "0"],
                 ["2024", "Training", "181", "20", "3", "3", "0", "0", "0"],
                 ["2025", "Training", "114", "29", "312", "271", "53", "68", "4"],
                 ["<b>Training total</b>", "", "1,285", "484", "7,263", "<b>5,808</b>", "388", "244", "166"],
                 ["<b>Test total</b>", "", "338", "193", "3,833", "<b>2,860</b>", "273", "114", "22"],
                 ["<b>All years</b>", "", "1,623", "677", "11,096", "8,668", "661", "358", "188"]],
                [0.10, 0.15, 0.10, 0.09, 0.10, 0.12, 0.11, 0.12, 0.11],
                "Consolidated dataset by year (2018 contributed 5 passes but no usable cases). A data point is one pass "
                "seen over one airport; 60 further matches lacked a complete set of measurements, giving 11,156 in total. "
                "Hazards are rare: thunderstorms appear in 8% of reported cases, rain within three hours in 4%, fog in 2%.",
                bold_last=3),
          figure("4_map_of_samples.png",
                 "Where the data comes from. Each circle is one of the 44 airports, sized by its number of "
                 "satellite–weather matches. Coverage is strongest in western and southern India, close to the best "
                 "receiving stations near Pune and Bangalore. Mountain airports such as Leh (74 matches) and Srinagar "
                 "(62) are represented but sparse.", 0.62 * TEXT_W)]

    # ── 6 Methodology ─────────────────────────────────────────
    s += [P("6. Methodology", "h1"), P("6.1 The satellite signal", "h2"),
          P("NOAA-15, 18 and 19 broadcast Automatic Picture Transmission (APT): an audio tone whose loudness "
            "carries brightness, sent at two image lines per second. Each line contains 2,080 values in a fixed "
            "layout (Figure 4): a sync pulse, a view of deep space, 909 pixels of image, and a strip of "
            "calibration wedges, repeated for two channels side by side. Channel A shows visible light by day and "
            "3.7 µm infrared at night; channel B always shows 10.8 µm thermal infrared, which measures how cold "
            "the cloud tops are. A pass lasts 10–15 minutes and gives 1,200–1,800 lines at about 4 km per pixel."),
          figure("sub_03_apt_anatomy.png",
                 "Anatomy of a real APT pass received near Bangalore. The left half is visible light (India's west "
                 "coast and Sri Lanka are clear); the right half is thermal infrared, in which cold cloud tops appear "
                 "white. The narrow vertical strips are the parts the software relies on: sync pulses mark the start "
                 "of each line, space views give a reference for the coldest possible reading, and the stepped grey "
                 "wedges (zoomed on the right) repeat every 128 lines to calibrate the image."),
          P("6.2 Cleaning", "h2")]
    s += bullets([
        "<b>Line alignment.</b> Each line is cross-correlated with the known seven-pulse, 1,040 Hz sync pattern to "
        "find where it starts, then shifted into place.",
        "<b>Noise rejection.</b> A line is kept only if its sync match is strong (correlation above 0.5) and its "
        "space-view strip is flat (interquartile range below 10), since a noisy radio link makes that strip rough.",
        "<b>Speckle removal.</b> A 3×3 median filter removes isolated interference dots.",
        "<b>Station screening.</b> Each ground station's six best passes are scored by the spread of brightness "
        "across columns. Real APT scores 5–50 because of its fixed stripes; pure static scores about 2, and such "
        "stations are skipped."])
    s += [P("6.3 Calibration to cloud-top temperature", "h2"),
          P("Every 128 lines the satellite sends 16 grey wedges. Wedges 1–8 are known brightness steps and wedge 9 "
            "is zero, so they map raw values onto a fixed scale whatever the radio's gain. Wedge 16 matches one of "
            "wedges 1–6 and identifies the channel shown. The infrared values are then converted to radiance "
            "<i>R</i> using two reference points the satellite also sends: deep space (count <i>C</i><sub>space</sub>, "
            "almost no radiance) and the satellite's internal warm target (count <i>C</i><sub>bb</sub>, radiance "
            "<i>R</i><sub>bb</sub>):"),
          equation("eq_radiance.png", 1),
          P("Planck's radiation law then turns radiance into brightness temperature <i>T</i>, using the channel's "
            "central wavenumber ν (925 cm<super>−1</super> for channel 4, 2,670 cm<super>−1</super> for channel 3B) "
            "and the radiation constants <i>c</i><sub>1</sub> = 1.191 × 10<super>−5</super> mW m<super>−2</super> "
            "sr<super>−1</super> cm<super>4</super> and <i>c</i><sub>2</sub> = 1.4388 K cm:"),
          equation("eq_planck.png", 2, 15 * mm),
          P("Cloud colder than 233 K (−40 °C) marks deep storm cloud, and colder than 220 K the very tallest tops. "
            "At night the difference between the 10.8 µm and 3.7 µm temperatures reveals fog, because fog "
            "droplets emit less at 3.7 µm."),
          P("6.4 Georeferencing", "h2"),
          P("The satellite's orbit (its two-line element set, TLE) gives its position for every line through the "
            "SGP4 orbit model. Each of the 909 pixels in a line is placed across the satellite's track, out to "
            "about 1,500 km on each side. We checked this by drawing real coastlines over clear daytime images "
            "(Figure 5). The check revealed that our first model spaced pixels by scan angle, which made India "
            "about 40% too wide; APT pixels are in fact evenly spaced in ground distance. Matching coastlines "
            "across a range of time shifts also showed that image lines start about 8 seconds later than the "
            "recording time, on all six clear passes tested. Both corrections are applied to every pass."),
          figure("sub_04_georef_check.png",
                 "The coastline check. Left: the first georeferencing model, in which the orange coastline (where the "
                 "software believes the coast is) is stretched sideways and Sri Lanka sits far east of the real island. "
                 "Right: after spacing pixels by ground distance and applying the measured timing offset, the orange "
                 "line follows the real coast of India and Sri Lanka. Without this check every data point would have "
                 "been matched to the wrong place."),
          P("6.5 Measuring the clouds around a location", "h2"),
          P("Around each airport in this study, or the trekker's GPS position on the device, the software measures "
            "46 inputs (Table 3). They describe how cold and how extensive the cloud is, whether it has the "
            "structure of a storm, how bright it looks in daylight, whether there is a fog signal at night, "
            "whether the clouds have grown since the previous pass, and how often hazards are normally reported "
            "there at that time of year and day."),
          table([["Group", "Examples of inputs", "Why it matters"],
                 ["Cloud-top temperature", "Coldest, 10th-percentile and median temperature; share colder than −40 °C",
                  "Taller, colder clouds produce storms"],
                 ["Storm structure", "Coldest top within 50 and 100 km; distance to the nearest storm cloud; "
                  "overshooting tops", "Overshooting tops mark strong updrafts in severe storms"],
                 ["Visible brightness (day)", "Cloud brightness; share of thick-and-cold against thin-and-cold cloud",
                  "Separates storm cloud from harmless thin cirrus"],
                 ["Night fog", "10.8 µm minus 3.7 µm temperature", "Positive over fog and low cloud"],
                 ["Cooling rate", "Change in coldest cloud top since a pass up to 4 hours earlier",
                  "Rapid cooling means a growing storm"],
                 ["Context", "Local time, month, viewing angle, the airport's hazard history",
                  "The same cloud means more on a monsoon afternoon"]],
                [0.22, 0.46, 0.32], "The 46 inputs, by group."),
          P("6.6 Prediction and the Climb Risk Score", "h2"),
          P("Gradient-boosted decision trees (scikit-learn's HistGradientBoostingClassifier) learn how the 46 inputs "
            "combine. One model is trained for each hazard: thunderstorm now, rain now, rain within three hours, "
            "and fog. A further model predicts the chance of <i>any</i> hazard, and its output is calibrated with "
            "isotonic regression so that a score of 30 means about a 30% chance. This becomes the Climb Risk "
            "Score, grouped into five bands with advice for the trekker. Two safety rules sit on top: if storm "
            "cloud colder than −40 °C is within 20 km, or an overshooting top is within 50 km, the score is never "
            "shown below High."),
          P("6.7 How results are measured", "h2"),
          P("The main measure is AUC, the probability that the system gives a real hazard a higher score <i>s</i> "
            "than a calm moment. An AUC of 0.5 is a coin toss and 1.0 is perfect:"),
          equation("eq_auc.png", 3, 8 * mm),
          P("The accuracy of the Climb Risk Score as a probability is measured by the Brier score <i>B</i>, the mean "
            "squared difference between the predicted probability <i>p</i> and what happened <i>o</i> (1 if a hazard "
            "was reported, 0 if not), and by its skill compared with local weather history:"),
          equation("eq_brier.png", 4, 13 * mm),
          equation("eq_skill.png", 5, 12 * mm),
          P("The baseline in every comparison is the airport's own hazard frequency for that month and three-hour "
            "time block, built from all reports outside the test year. TrailSky has to beat it to show that the "
            "satellite adds information.")]

    # ── 7 Development ─────────────────────────────────────────
    s += [P("7. How the algorithm was developed", "h1"),
          P("The algorithm went through three versions. Each was replaced because testing on real data showed "
            "what it got wrong (Table 4)."),
          table([["Version", "How it decides", "What real data showed"],
                 ["v1 (original)", "Fixed brightness thresholds, chosen by hand and tuned on simulated images",
                  "Caught 0 of 37 thunderstorms; its fog alert was right 3% of the time"],
                 ["v2", "Cloud-top temperature thresholds and a logistic regression on 20 inputs",
                  "Caught about 70% of storms, but only matched local history for thunderstorms"],
                 ["v3 (final)", "Gradient-boosted trees on 46 inputs, calibrated Climb Risk Score and safety rules",
                  "Beats local history for thunderstorms and rain on an unseen year; risk bands match reality"]],
                [0.15, 0.45, 0.40], "The three versions of the algorithm."),
          P("Seven problems were found and fixed along the way, each by checking against real data:")]
    s += bullets([
        "<b>The original images were simulated</b>, so every earlier score was circular. We switched to real archived passes.",
        "<b>\"Good\" passes that were pure static.</b> The busiest regional station produced 185 passes of noise; "
        "automatic station screening now rejects such stations.",
        "<b>India drawn 40% too wide</b>, found with the coastline check (Figure 5) and fixed.",
        "<b>An 8-second timing offset</b>, about 50 km along the track, measured on six clear passes and corrected.",
        "<b>The night channel was mislabelled</b> as 3A, which only sees sunlight; it was really 3B, which made the "
        "night fog test possible.",
        "<b>Good image sections were discarded</b> when surrounded by noise; calibration now uses clean lines only, "
        "with a whole-pass fallback.",
        "<b>A baseline too weak to be fair</b> was rebuilt from each airport's full history, which made the test harder "
        "for the satellite, not easier."])

    # ── 8 Training and testing ────────────────────────────────
    s += [P("8. Training and testing", "h1"),
          P("The model was trained on 5,808 cases from every year except 2019 and tested once on the 2,860 cases "
            "from 2019, roughly a two-thirds to one-third split (Figure 6). Splitting by whole year keeps the test "
            "honest: cases from the same satellite pass or the same spell of weather never appear on both sides. "
            "All settings, alert thresholds, the risk calibration and the safety-rule floors were fixed using 2020 "
            "data before any 2019 case was scored. The local-history baseline was also rebuilt without 2019."),
          figure("sub_02_train_test.png",
                 "Training and test design. Each box is one year with its number of cases that have an airport report; "
                 "the bars below show their relative size. 2019 (orange) is held out until the end. 2020 is part of "
                 "training but is also used to choose settings and calibrate the risk score. The locked model then "
                 "predicts each 2019 case exactly once."),
          P("2019 was chosen because it is large enough for a reliable test while leaving most data for training. "
            "2021 is larger but holds more cases than all other years combined, so holding it out would have left "
            "less data for training than for testing. To check that the result does not depend on this choice, "
            "the same test was repeated holding out each other year in turn.")]

    # ── 9 Results ─────────────────────────────────────────────
    s += [P("9. Results on the 2019 test year", "h1"),
          P("On 2,860 cases the model never saw, the satellite beat local weather history for thunderstorms and "
            "for rain (Figure 7 and Table 5), which supports the hypothesis for those hazards."),
          figure("iris_1_test2019_detection.png",
                 "Detection on the 2019 test year. Each panel plots, for every possible alert threshold, the share of "
                 "real events caught (up) against the share of calm moments wrongly alerted (right). A curve closer to "
                 "the top-left corner is better; the faint diagonal is guessing. Solid navy is TrailSky v3, dashed grey "
                 "is the airport's weather history. TrailSky is clearly better for thunderstorms and both rain targets; "
                 "for fog the two curves lie on top of each other."),
          table([["Hazard", "Cases", "TrailSky AUC", "Local history AUC", "Caught (safety)", "Alerts correct (safety)",
                  "Caught (balanced)", "Alerts correct (balanced)"],
                 ["Thunderstorm now", "273", "<b>0.90</b>", "0.81", "70%", "40%", "54%", "54%"],
                 ["Rain within 3 hours", "114", "<b>0.88</b>", "0.68", "69%", "17%", "40%", "21%"],
                 ["Rain now", "87", "<b>0.88</b>", "0.69", "83%", "12%", "51%", "19%"],
                 ["Fog now", "22", "0.98", "<b>0.99</b>", "86%", "17%", "50%", "22%"]],
                [0.18, 0.08, 0.11, 0.12, 0.12, 0.13, 0.12, 0.14],
                "Results on the 2019 test year. The safety setting is tuned to miss as few hazards as possible; the "
                "balanced setting trades some catches for fewer false alarms. Both were fixed on 2020 data before the test."),
          P("For thunderstorms, the main danger on exposed trails, the gain over local history is large: AUC rises "
            "from 0.81 to 0.90. The improvement is largest for rain within three hours (0.68 to 0.88), which is "
            "the most useful warning for a trekker deciding whether to set out. Fog is the exception: with only 22 "
            "fog cases in 2019, and fog mostly predictable from the season and hour, the satellite adds nothing "
            "measurable."),
          P("Choosing an alert threshold is a trade-off (Figure 8). The hiker-safety setting catches 70% of "
            "thunderstorms, and 40% of its alerts are followed by a reported storm. That is four times better than "
            "random alerts, which would be right 10% of the time. The balanced setting raises fewer false alarms "
            "but misses more storms. For a trekker on a ridge a missed storm costs far more than an unnecessary "
            "turn-back, so TrailSky uses the safety setting."),
          figure("sub_05_tradeoff_2019.png",
                 "The thunderstorm alert trade-off on 2019. The curve shows every possible threshold: further right "
                 "catches more storms, higher up means more alerts are correct. The orange point is the hiker-safety "
                 "setting (70% caught, 40% correct), the navy point the balanced setting (54% caught, 54% correct). "
                 "The dashed line is the accuracy of random alerts.", 0.85 * TEXT_W),
          P("Figure 9 shows which inputs the thunderstorm model relies on. The airport's own storm history matters "
            "most, as expected, but the next most important inputs are all satellite storm features: overshooting "
            "tops within 100 km, the coldest cloud top within 100 km and the area of deep storm cloud nearby. These "
            "are the signs forecasters use to recognise severe storms, which suggests the model has learned real "
            "atmospheric physics rather than coincidences in the data."),
          figure("3_feature_importance_thunder_now.png",
                 "What the thunderstorm model relies on. Each bar is the drop in accuracy (average precision) when that "
                 "input is scrambled, measured on the 2020 tuning data and averaged over all held-out years. After "
                 "local history, satellite storm-structure features dominate.", 0.85 * TEXT_W),
          P("<b>Robustness.</b> Repeating the whole procedure with each other year held out gave thunderstorm AUCs of "
            "0.93 for 2021 and 0.85 for 2022–2025 combined (369 cases, from noisier recordings). The result does not "
            "depend on the choice of test year.")]

    # ── 10 Climb Risk Score ───────────────────────────────────
    s += [P("10. The Climb Risk Score", "h1"),
          P("The Climb Risk Score turns the model into a single number a trekker can act on. On 2019 it ranked "
            "hazards with an AUC of 0.89, and its prediction error (Brier score 0.073) was 21% lower than predicting "
            "from local history alone (0.092; equations 4 and 5). Most importantly, its bands mean what they say "
            "(Figure 10)."),
          figure("iris_2_test2019_risk_bands.png",
                 "Climb Risk bands on 2019. Each bar is the share of cases in that band where a thunderstorm, rain within "
                 "three hours or fog was reported. The rate rises steadily from 3% (Minimal) through 18%, 32% and 47% to "
                 "74% (Extreme). Most cases (69%) fall in Minimal, so the device is not constantly raising alarms.",
                 0.85 * TEXT_W),
          table([["Band", "Score", "Share of cases", "Hazard reported", "Advice shown"],
                 ["Minimal", "0–10", "69%", "3%", "Conditions favourable; keep checking each pass"],
                 ["Low", "10–25", "18%", "18%", "Monitor conditions"],
                 ["Moderate", "25–45", "2%", "32%", "Proceed with caution; set a turn-around time"],
                 ["High", "45–70", "8%", "47%", "Avoid exposed ridges; consider turning back"],
                 ["Extreme", "70–100", "2%", "74%", "Do not climb"]],
                [0.13, 0.10, 0.15, 0.15, 0.47], "Climb Risk bands, 2019 test year, and the advice the device shows."),
          P("A score is only useful if it is honest: a score of 30 should be followed by a hazard about 30% of the "
            "time. Figure 11 checks this. Up to a score of about 75 the points lie close to the diagonal; at the very "
            "top the score is slightly overconfident, with the highest bin coming true 80% of the time. No score "
            "should therefore be read as certainty."),
          figure("iris_3_test2019_calibration.png",
                 "Is the score honest? Cases are grouped by the score they received (across); the height shows how often "
                 "a hazard was then reported. Points on the dashed diagonal would be perfectly honest. Dot size shows the "
                 "number of cases; only groups with at least 15 cases are shown.", 0.6 * TEXT_W),
          P("The two safety rules were confirmed on years the model never saw: when storm cloud was within 20 km a "
            "hazard followed 54% of the time (437 cases), and when an overshooting top was within 50 km, 56% of the "
            "time (500 cases). Both are above the High band's starting score of 45, which justifies never showing "
            "less than High in those situations.")]

    # ── 11 Case studies ───────────────────────────────────────
    s += [P("11. Case studies", "h1"),
          P("Two real passes, both from years the predicting model never saw, show the system at its best and at "
            "its weakest. In both images white is very cold cloud top, dark is warm ground or sea, orange outlines "
            "mark cloud colder than −40 °C, the triangle is the airport and white stripes are noisy lines the "
            "software removed."),
          figure("5_case_1_caught_VEBS.png",
                 "Caught: Bhubaneswar, 17 August 2023, 10:30 IST, NOAA-18. A large storm system covers the airport, "
                 "with the nearest storm cloud 3 km away and cloud tops at −82 °C. TrailSky gave the maximum Climb Risk "
                 "Score (Extreme), and the airport reported a thunderstorm with rain.", 0.75 * TEXT_W),
          figure("5_case_2_missed_VOCI.png",
                 "Missed: Kochi, 15 August 2025, 19:04 IST, NOAA-15. Storm cells are visible, but the nearest was 99 km "
                 "away and the sky over the airport was not storm-cold, so the score was 15 (Low). A thunderstorm was "
                 "nevertheless reported, most likely because it formed or drifted in after the pass. This is the "
                 "system's main weakness: it sees one snapshot every few hours.", 0.75 * TEXT_W)]

    # ── 12 Future scope ───────────────────────────────────────
    s += [P("12. Future scope", "h1"), P("12.1 Moving to current satellites", "h2"),
          P("NOAA-15, 18 and 19 stopped broadcasting APT in 2025, so a production device needs a satellite that is "
            "still transmitting. Russia's Meteor-M satellites send LRPT images on the same 137 MHz band with similar "
            "infrared channels. The antenna, radio and most of this method carry over; the decoder and calibration "
            "step change, and the models would be retrained on archived Meteor-M passes."),
          P("12.2 Use by trekking companies and rescue teams", "h2"),
          table([["User", "How they would use TrailSky", "What it changes"],
                 ["Trek leaders and guides", "Check the Climb Risk Score at each pass before summit day or a high crossing",
                  "Go/no-go calls backed by a satellite view, not only experience"],
                 ["Trekking companies", "One device per group, with company rules such as turning back at High",
                  "Consistent safety decisions across guides and groups"],
                 ["Safety managers", "Download each device's log of passes, scores and decisions after a trek",
                  "Audits and incident reviews based on real data"],
                 ["Mountain rescue teams", "Check the risk over a search area before sending people or helicopters",
                  "Safer timing of operations"],
                 ["Pilgrimage and park authorities", "Fixed units at base camps on busy high routes",
                  "Warnings for many people where coverage is poor"]],
                [0.24, 0.42, 0.34], "How organisations could use TrailSky."),
          Placeholder("TrailSky in use on a trail", "Photo of a guide checking the device before a crossing", 65 * mm),
          P("12.3 Improving the model", "h2")]
    s += bullets([
        "<b>Better rain truth</b> from satellite rainfall estimates (for example NASA's GPM, every 30 minutes on a "
        "10 km grid), covering mountains with no airport.",
        "<b>Lightning data</b> to check thunderstorm warnings directly.",
        "<b>Field feedback:</b> every TrailSky trek logs its predictions; guides marking what actually happened would "
        "add the mountain data that airports cannot provide.",
        "<b>Route-aware warnings</b> that score the whole planned route, so a group knows which pass to cross first."])

    # ── 13 Limitations ────────────────────────────────────────
    s += [P("13. Limitations", "h1")]
    s += bullets([
        "<b>Storms between passes are missed.</b> One satellite view every few hours means about 3 in 10 thunderstorms "
        "were missed in the test year.",
        "<b>Rain alerts include many false alarms</b>, because rain is reported in only 3–4% of cases; this was a "
        "deliberate choice in favour of safety.",
        "<b>Fog comes from history, not the satellite</b>, and 2019 had only 22 fog cases.",
        "<b>Recent data is scarce.</b> Recordings from 2022–2025 were mostly too noisy; on those years thunderstorm AUC "
        "was 0.85 from 369 cases.",
        "<b>Ground truth is at airports</b>, which can be tens of kilometres from a trail, and mountain airports report less.",
        "<b>Coverage is uneven</b>, favouring western and southern India.",
        "<b>Temperatures are approximate</b> by a few kelvin, because the satellite's warm target is assumed at 290 K.",
        "<b>Archived recordings, not a field prototype.</b> A live field test of the device is the most important next step."])

    # ── 14 Conclusion ─────────────────────────────────────────
    s += [P("14. Conclusion", "h1"),
          P("Using only public archives, this project built and tested a complete chain from raw weather-satellite "
            "recordings to a trekker's Climb Risk Score. The original alert logic, designed on simulated images, "
            "failed on real data. The rebuilt system, tested on a year it never saw, detected thunderstorms and rain "
            "clearly better than local weather history, and its risk score proved honest across its range. The "
            "satellite adds real information exactly where trekkers need it most: storms and rain, in places with "
            "no signal. TrailSky cannot guarantee safety, but it gives a trekker a measured, satellite-based view "
            "of the sky overhead to support their own judgement.")]

    # ── 15 References ─────────────────────────────────────────
    s += [P("15. Data sources and acknowledgements", "h1")]
    s += bullets([
        "SatNOGS Network, network.satnogs.org: archived NOAA APT images and pass orbit data, CC BY-SA 4.0.",
        "Iowa Environmental Mesonet, mesonet.agron.iastate.edu: METAR reports for 44 Indian airports, 2018–2025.",
        "Open-Meteo historical weather API (ERA5 reanalysis), open-meteo.com: cross-check of cloud and rain, CC BY 4.0.",
        "Natural Earth, naturalearthdata.com: coastlines for the georeferencing check, public domain.",
        "Software: pyorbital (orbits), scikit-learn (models), NumPy, SciPy and Matplotlib (analysis and figures)."])
    s += [P("Thanks to the SatNOGS volunteers whose ground stations recorded every pass used here. No personal "
            "data was stored; all 44 locations are public airports.")]
    return s


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=20 * mm, bottomMargin=18 * mm,
                          title="TrailSky: satellite storm warnings for trekkers",
                          subject="IRIS National Fair submission")
    frame = Frame(MARGIN, 18 * mm, TEXT_W, PAGE_H - 38 * mm, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(story())
    print(OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    build()
