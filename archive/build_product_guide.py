"""
Builds the product guide: how SummitSathi works end to end (Meteor-M edition).

    python -m archive.build_product_guide      # → ~/Downloads/SummitSathi_How_It_Works.pdf
"""
import json
from pathlib import Path
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Spacer, PageBreak, Table, TableStyle

sys.path.insert(0, str(Path(__file__).parent.parent))
import archive.build_submission_pdf as bs
from archive.build_submission_pdf import P, bullets, table, figure, Placeholder, TEXT_W, MARGIN, PAGE_W, PAGE_H
from archive.build_submission_pdf import MUTED, RULE, PANEL, FIG

OUT = Path.home() / "Downloads" / "SummitSathi_How_It_Works.pdf"
PASS = json.loads((FIG / "prod_pass.json").read_text())
DAY = json.loads((FIG / "prod_day_passes.json").read_text())


def panel(text):
    return Table([[P(text, "body")]], colWidths=[TEXT_W],
                 style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

def step(title, what, how, why):
    out = [P(title, "h2"), P(f"<b>What happens.</b> {what}")]
    out += [P("<b>How.</b>", "body")] + bullets(how) if isinstance(how, list) else [P(f"<b>How.</b> {how}")]
    out.append(P(f"<b>Why.</b> {why}"))
    return out


def on_page(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 13 * mm, PAGE_W - MARGIN, PAGE_H - 13 * mm)
    canvas.setFont("Helvetica", 7.8); canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, PAGE_H - 11 * mm, "How SummitSathi works")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 11 * mm, "Product guide · Meteor-M edition")
    canvas.drawCentredString(PAGE_W / 2, 10 * mm, str(doc.page))
    canvas.restoreState()


def story():
    bs.fig_no[0] = 0
    bs.tab_no[0] = 0
    good = [p for p in DAY if p["max_el"] >= 30]
    s = [Spacer(1, 30 * mm), P("How SummitSathi works", "title"), Spacer(1, 3 * mm),
         P("A complete guide to the product, from the weather satellite overhead to the warning on the screen. "
           "Meteor-M edition.", "subtitle"), Spacer(1, 10 * mm),
         Placeholder("SummitSathi device with antenna deployed", "Photo of the receiver in use outdoors", 80 * mm),
         Spacer(1, 8 * mm),
         panel("<b>In one paragraph.</b> SummitSathi listens for Russia's Meteor-M weather satellites as they pass "
               "overhead. Its antenna and radio record the satellite's digital LRPT broadcast at 137 MHz for about "
               "12 minutes. The on-board computer turns that signal back into cloud images, converts the images "
               "into cloud-top temperatures, places them on the map, and measures the clouds around the trekker's "
               "GPS position. Trained models then turn those measurements into a 0–100 Climb Risk Score with "
               "plain-language advice. Everything happens on the device, with no phone signal or internet."),
         PageBreak()]

    # ── 1 Big picture ─────────────────────────────────────────
    s += [P("1. The big picture", "h1"),
          P("SummitSathi does three jobs, one after another: it <b>receives</b> a satellite broadcast, it <b>decodes</b> "
            "that broadcast back into images, and it <b>interprets</b> the images into a warning. Figure 1 shows "
            "every part involved, from the satellite to the screen."),
          figure("prod_01_system.png",
                 "The whole system. The top row is the radio chain that catches the signal. The large box is the "
                 "on-board computer, where seven software stages turn the signal into a score. The dashed boxes are "
                 "supporting inputs, and the orange boxes are what the trekker sees."),
          P("The radio chain (antenna, filter, amplifier, radio receiver) works only while a satellite is overhead, "
            "about 12 minutes at a time. The computer does its work in the minute or two after each pass. Between "
            "passes the device mostly waits, keeping the last result on screen and counting down to the next pass.")]

    # ── 2 Satellites ──────────────────────────────────────────
    s += [P("2. Where the data comes from: the Meteor-M satellites", "h1"),
          P("SummitSathi currently receives <b>Meteor-M N2-3</b> and <b>Meteor-M N2-4</b>, Russian polar-orbiting weather "
            "satellites launched in 2023 and 2024. They broadcast their images openly, free of charge and without "
            "encryption, so anyone with a suitable antenna and receiver can pick them up."),
          P("2.1 The orbit", "h2"),
          P("Both satellites fly about 830 km up in a <b>sun-synchronous polar orbit</b>, inclined about 98.6° to the "
            "equator. Each orbit takes about 101 minutes, so a satellite goes round the Earth just over 14 times a "
            "day. Because the Earth turns underneath, each orbit passes over a different strip. Because the orbit is "
            "sun-synchronous, a satellite crosses any given place at roughly the same local times every day."),
          table([["Satellite", "Rises (IST)", "Highest (IST)", "Sets (IST)", "Max elevation", "Length (min)"]] +
                [[p["sat"], p["rise"], p["peak"], p["set"], f"{p['max_el']}°", p["mins"]] for p in DAY],
                [0.2, 0.15, 0.17, 0.15, 0.17, 0.16],
                f"Every Meteor-M pass over Manali on {PASS['date']}, calculated from current orbit data. "
                f"{len(good)} passes rise above 30° and give good images; low passes (under about 20°) are weak and "
                "noisy."),
          P(f"On this example day the good passes come at about {', '.join(p['peak'] for p in good)} IST, roughly "
            "one every five and a half to seven hours. That spacing is the single most important limit of the product: "
            "SummitSathi sees the sky as a series of snapshots, and a storm that builds between two snapshots can be missed."),
          P("2.2 The camera on board: MSU-MR", "h2"),
          P("Each satellite carries a scanning radiometer called MSU-MR. A rotating mirror sweeps across the ground "
            "from side to side while the satellite moves forward, so the image is built up one line at a time, "
            "about 2,800 km wide and about 1 km per pixel directly below the satellite. It measures six wavelengths:"),
          table([["Channel", "Wavelength (µm)", "What it sees", "Use in SummitSathi"],
                 ["1", "0.5–0.7", "Visible light (daytime only)", "Cloud brightness: thick storm cloud vs thin cloud"],
                 ["2", "0.7–1.1", "Near infrared (daytime only)", "Land, water and cloud contrast"],
                 ["3", "1.6–1.8", "Short-wave infrared (daytime only)", "Telling snow and ice from cloud"],
                 ["4", "3.5–4.1", "Mid infrared (day and night)", "Night fog: fog emits less here than at 11 µm"],
                 ["5", "10.5–11.5", "Thermal infrared (day and night)", "Cloud-top temperature, the main storm signal"],
                 ["6", "11.5–12.5", "Thermal infrared (day and night)", "Second temperature view; thin high cloud"]],
                [0.11, 0.17, 0.32, 0.40], "MSU-MR channels."),
          P("Thermal infrared is the key channel. Every surface glows in infrared according to its temperature, so "
            "the camera effectively measures how cold the top of each cloud is. Tall thunderstorm clouds reach 12–16 km "
            "high, where the air is −50 to −80 °C, so their tops look very cold. Low cloud and clear ground look warm."),
          P("2.3 The broadcast: LRPT", "h2"),
          P("The satellites broadcast a reduced version of the camera data called <b>LRPT</b> (Low Rate Picture "
            "Transmission) on about 137 MHz. LRPT carries <b>three of the six channels</b> at a time, chosen by the "
            "satellite's operators (typically visible and infrared channels by day, infrared at night), at about "
            "72 kilobits per second. Unlike the older NOAA APT broadcast, which was an analogue audio tone, LRPT is fully "
            "digital and compressed, like sending JPEG photos over a slow radio link."),
          table([["", "NOAA APT (used in the study)", "Meteor-M LRPT (current product)"],
                 ["Status", "Switched off in 2025", "Broadcasting"],
                 ["Signal type", "Analogue audio tone", "Digital (QPSK), error-corrected"],
                 ["Resolution", "About 4 km per pixel", "About 1 km per pixel"],
                 ["Channels sent", "2", "3"],
                 ["With noise", "Picture gets grainy but stays readable", "Decodes cleanly, or drops whole strips"],
                 ["Calibration in the signal", "Grey wedges every 128 lines", "No calibration wedges; see section 4.6"],
                 ["Decoding", "Simple", "Several layers (section 4)"]],
                [0.24, 0.38, 0.38], "The old and new satellite broadcasts compared.")]

    # ── 3 Hardware ────────────────────────────────────────────
    s += [P("3. The hardware, part by part", "h1"),
          P("Every part exists to solve one problem: catching a very weak signal from a satellite 900–2,800 km away, "
            "then processing it in the field on battery power. Table 4 lists each part by its job. The exact models "
            "are given in the product specification and the photo spaces below are for the real device."),
          table([["Part", "What it does", "Why it is needed"],
                 ["Antenna (137 MHz, quadrifilar helix or V-dipole)",
                  "Collects the satellite's radio waves from most of the sky",
                  "The satellite moves across the whole sky in 12 minutes, so the antenna must not need pointing. "
                  "The satellite's signal is circularly polarised; a matching antenna avoids deep fades as its angle changes."],
                 ["Coaxial cable", "Carries the signal from the antenna into the device",
                  "Kept short, because every metre of cable loses some of an already weak signal"],
                 ["Band filter", "Blocks strong nearby signals, especially FM radio (88–108 MHz)",
                  "A strong FM station can overload the receiver and drown the satellite"],
                 ["Low-noise amplifier (LNA)", "Boosts the signal before it travels further",
                  "Placed near the antenna so the signal is strengthened before cable and receiver add noise"],
                 ["Software-defined radio (SDR)", "Tunes to 137 MHz and converts the radio wave into digital samples",
                  "Lets all demodulation and decoding happen in software, so new satellites only need a software update"],
                 ["On-board computer", "Runs the whole software chain: scheduling, decoding, maps, models and screen",
                  "Must decode about 12 minutes of signal and run the models within a minute or two, on battery"],
                 ["Storage", "Holds the operating system, orbit data, trained models, maps and recent passes",
                  "Everything must be on the device because there is no internet in the field"],
                 ["GPS receiver", "Gives the trekker's position and very accurate time",
                  "Position tells the model where to look; time matters because a one-second error moves the map about 7 km"],
                 ["Real-time clock", "Keeps time when there is no GPS fix",
                  "Pass predictions need the time even indoors or before the GPS locks"],
                 ["Screen and buttons", "Show the score, advice and next pass; work with gloves",
                  "Must be readable in bright sun and usable in the cold"],
                 ["Battery and power board", "Power everything for a full day; manage charging",
                  "A trek has no mains power; the radio and computer run for every pass"],
                 ["Enclosure", "Protects the electronics from rain, dust and drops; shields the radio",
                  "The computer's own electronics create noise that can interfere with the weak signal"]],
                [0.22, 0.34, 0.44], "Each part of SummitSathi and its job."),
          Placeholder("Inside the device, parts labelled", "Antenna connector, filter/LNA, SDR, computer, GPS, battery", 70 * mm),
          Placeholder("Antenna deployed", "The 137 MHz antenna in its operating position", 55 * mm)]

    # ── 4 Journey ─────────────────────────────────────────────
    s += [P("4. The journey of one pass, step by step", "h1"),
          P("This section follows a single satellite pass through the product, from knowing when to listen to "
            "showing the warning. Each step says what happens, how, and why it is done that way.")]
    s += step("4.1 Knowing when to listen",
              "The device works out in advance exactly when each satellite will rise above the horizon, how high it "
              "will climb and when it will set.",
              ["It stores each satellite's <b>orbital elements</b> (TLE), two lines of numbers describing the orbit, "
               "refreshed whenever a connection is available, for example at the trailhead.",
               "An orbit model called <b>SGP4</b> moves each satellite forward in time and compares its position with "
               "the trekker's GPS position.",
               "It schedules the radio to start a minute or two before each pass rises above about 5°."],
              "The satellite is only in view for about 12 minutes at a time. Listening at the wrong moment wastes "
              "battery and catches nothing. Orbital elements slowly go out of date, so they should be refreshed "
              "every week or two.")
    s += [figure("prod_03_pass.png",
                 f"A real upcoming pass: Meteor-M2 3 over Manali on {PASS['date']}. Top: the satellite rises at "
                 f"{PASS['rise_ist']} IST, climbs to {PASS['max_el']}° at {PASS['peak_ist']} and sets at "
                 f"{PASS['fall_ist']}, a {PASS['duration_min']}-minute pass. Middle: its distance falls from "
                 f"{PASS['max_range']:,} km to {PASS['min_range']} km and rises again. Bottom: the Doppler shift of its "
                 f"radio frequency swings from +{PASS['doppler_khz']} to −{PASS['doppler_khz']} kHz.", 0.85 * TEXT_W)]
    s += step("4.2 Catching the signal",
              "The antenna, filter, amplifier and radio receiver capture the satellite's broadcast and turn it into "
              "a stream of numbers the computer can process.",
              ["The radio tunes to the satellite's frequency (about 137.1 or 137.9 MHz, depending on the satellite).",
               "It converts the signal into <b>I/Q samples</b>: about one to two million pairs of numbers per second, "
               "describing the strength and timing (phase) of the wave.",
               "The software corrects for the <b>Doppler shift</b>: as the satellite approaches, its frequency appears "
               f"higher, and as it leaves, lower, by up to about ±{PASS['doppler_khz']} kHz (Figure 2, bottom)."],
              "The signal is weakest when the satellite is low and far away (2,800 km) and strongest overhead "
              "(about 900 km), so the edges of a pass are noisy. Correcting the Doppler shift keeps the receiver locked on.")
    s += step("4.3 Demodulation: from radio wave to bits",
              "The software recovers the stream of 1s and 0s that the satellite sent.",
              ["LRPT uses <b>QPSK</b>: the wave's phase jumps between four positions, and each position stands for two bits.",
               "A filter matched to the transmitter's pulse shape removes noise; a tracking loop locks onto the exact "
               "carrier frequency and phase; a timing loop finds the exact moment to read each symbol.",
               "The output is 72,000 <b>soft bits</b> per second: not just 0 or 1, but how confident each one is."],
              "Keeping the confidence of each bit lets the next stage correct errors far better than hard 0/1 decisions would.")
    s += [figure("prod_02_decode_stack.png",
                 "The layers between the radio wave and the picture. Each layer either strips away a layer of "
                 "protection the satellite added, or repairs errors caused by noise on the way.", 0.95 * TEXT_W)]
    s += step("4.4 Decoding: repairing and unpacking the data",
              "The software repairs the damage noise has done and unpacks the image data, following the international "
              "CCSDS standard for spacecraft data.",
              ["<b>Viterbi decoding:</b> the satellite sends every data bit twice in a clever coded form (a rate-½ "
               "convolutional code), and the decoder uses that redundancy to work out the most likely original bits.",
               "<b>Frame sync:</b> the decoder searches for a fixed marker (1ACFFC1D in hexadecimal) that starts every "
               "1,024-byte frame, so it knows where each block of data begins.",
               "<b>Derandomisation:</b> the satellite scrambled the data with a known pattern, to avoid long runs of "
               "identical bits; the decoder undoes it.",
               "<b>Reed–Solomon correction:</b> a second error-correcting code fixes up to 16 wrong bytes in each block.",
               "<b>Packets:</b> frames contain packets; each packet's ID number (APID 64–69) says which camera channel "
               "it belongs to."],
              "The two error-correcting codes are why a digital broadcast gives clean images even from a weak signal. "
              "When the noise is too strong for them, a block is lost completely and appears as a short black strip.")
    s += step("4.5 Rebuilding the image",
              "The packets are turned back into three images, one per channel.",
              ["Each packet holds a strip of <b>8×8-pixel blocks</b>, compressed like a JPEG photo: the brightness pattern "
               "of each block is stored as a few frequency coefficients rather than 64 separate values.",
               "The decoder reverses the compression and places each block in its row and column.",
               "Rows 8 pixels tall build up line by line into images about 1,568 pixels wide, covering the full "
               "2,800 km swath."],
              "Compression lets 1 km-resolution images fit through a slow 72 kbit/s link. The cost is small "
              "compression errors and black strips where packets were lost.")
    s += step("4.6 From pixels to physics",
              "Each pixel's brightness value (0–255) is turned into a physical quantity: cloud-top temperature for the "
              "infrared channels, and cloud brightness for the visible channels.",
              ["For the thermal channel, brighter or darker values map onto colder or warmer temperatures through a "
               "calibration scale.",
               "Unlike NOAA APT, LRPT does not carry calibration wedges in the signal, so the scale has to be "
               "established separately for each satellite, for example by comparing decoded images with calibrated "
               "reference data for the same passes.",
               "Clouds colder than about −40 °C (233 K) indicate deep storm cloud; colder than about −53 °C (220 K), "
               "the very tallest tops."],
              "The models reason about temperatures, not raw pixel values. A reliable temperature scale is what lets a "
              "model trained on one set of passes work on another. Setting up this scale is one of the main engineering "
              "tasks for the Meteor-M version.")
    s += step("4.7 Placing the image on the map",
              "Every pixel is given a latitude and longitude, so the device knows which pixels are above the trekker.",
              ["The orbit model gives the satellite's position and direction for the moment each line was scanned.",
               "The camera's scan geometry gives the direction of each pixel across the line. Pixels near the edges of "
               "the swath look at the ground at a slant and cover more ground than those directly below.",
               "The result is checked against real coastlines, the same check that caught two errors in the study."],
              "If the map is wrong, the device measures the wrong clouds. In the study a timing error of a few seconds "
              "moved the image by tens of kilometres, and an incorrect pixel spacing made India 40% too wide; both "
              "were found only by checking against coastlines.")
    s += step("4.8 Measuring the clouds around the trekker",
              "The software looks at the pixels around the trekker's GPS position and calculates 46 measurements.",
              ["<b>How cold:</b> the coldest and typical cloud-top temperatures nearby, and how much cloud is colder than −40 °C.",
               "<b>Storm structure:</b> the coldest cloud within 50 and 100 km, the distance to the nearest storm cloud, "
               "and overshooting tops (cold bumps where strong updrafts punch upward).",
               "<b>Brightness (daytime):</b> thick, bright storm cloud versus thin, dim high cloud that is harmless.",
               "<b>Fog (night):</b> the difference between the 11 µm and 3.7 µm temperatures, positive over fog.",
               "<b>Growth:</b> how much colder the clouds became since the previous pass, if one was within 4 hours.",
               "<b>Context:</b> time of day, month, viewing angle and the area's normal hazard frequency."],
              "A single temperature value cannot tell a dangerous storm from harmless high cloud. Combining size, "
              "structure, brightness and growth gives the models a much clearer picture.")
    s += step("4.9 Predicting the risk",
              "Trained models turn the 46 measurements into the chance of each hazard and a single Climb Risk Score.",
              ["<b>Hazard models</b> (gradient-boosted decision trees) estimate the chance of a thunderstorm now, rain "
               "now, rain within three hours, and fog.",
               "A <b>risk model</b> estimates the chance of any hazard, calibrated so that a score of 30 means about a 30% chance.",
               "<b>Safety rules</b> override the model: if storm cloud colder than −40 °C is within 20 km, or an "
               "overshooting top is within 50 km, the score is never shown below High."],
              "The models learn the combinations that matter from thousands of real cases, rather than relying on "
              "hand-picked thresholds, which failed when tested on real data. The safety rules make sure the device "
              "is never confidently wrong in the dangerous direction.")
    s += step("4.10 Showing the result",
              "The screen shows what the trekker needs to decide, in plain language.",
              ["<b>Score and band:</b> 0–100 and Minimal, Low, Moderate, High or Extreme, colour-coded green to red.",
               "<b>Advice:</b> for example \"Avoid exposed ridges; consider turning back\".",
               "<b>Reasons:</b> for example \"Storm cloud 12 km away\" or \"Cloud tops cooling 8 °C per hour, storm growing\".",
               "<b>Status:</b> <i>Current</i>; <i>Stale</i> if the last pass is more than three hours old; or "
               "<i>No data</i> if the device has no usable view of the trekker's position. It never shows \"safe\" by default.",
               "<b>Next pass:</b> a countdown to the next satellite."],
              "A number alone is not enough to act on. Advice and reasons let the trekker understand and trust the "
              "warning, and the status flags stop an old or missing view being mistaken for good news.")
    s += [table([["Band", "Score", "Hazard rate when tested*", "Advice shown"],
                 ["Minimal", "0–10", "3%", "Conditions favourable; keep checking each pass"],
                 ["Low", "10–25", "18%", "Monitor conditions"],
                 ["Moderate", "25–45", "32%", "Proceed with caution; set a turn-around time"],
                 ["High", "45–70", "47%", "Avoid exposed ridges; consider turning back"],
                 ["Extreme", "70–100", "74%", "Do not climb"]],
                [0.14, 0.12, 0.24, 0.50],
                "The Climb Risk bands. *Hazard rates measured on the 2019 test year of the NOAA study; they must be "
                "re-measured for Meteor-M (section 6)."),
          Placeholder("Climb Risk Score screen", "Screen showing score, band, advice, reasons and next-pass countdown", 65 * mm)]

    # ── 5 Timeline ────────────────────────────────────────────
    s += [P("5. One pass, minute by minute", "h1"),
          P(f"Using the real Meteor-M2 3 pass over Manali on {PASS['date']} (Figure 2):"),
          table([["Time (IST)", "What the device is doing"],
                 ["Earlier that day", "Calculates the day's passes from stored orbit data and schedules this one"],
                 ["About 09:25", "Wakes the radio, tunes to the satellite's frequency, starts recording"],
                 [f"{PASS['rise_ist']}", "Satellite rises at 5°, 2,800 km away; the signal is weak and mostly noise"],
                 ["About 09:29–09:31", "Signal strengthens above about 15–20°; demodulator locks; clean frames start arriving"],
                 [f"{PASS['peak_ist']}", f"Highest point, {PASS['max_el']}° and {PASS['min_range']} km away; the strongest, cleanest signal"],
                 ["About 09:37–09:39", "Signal weakens again as the satellite sinks; some blocks are lost"],
                 [f"{PASS['fall_ist']}", "Satellite sets; recording stops"],
                 ["About 09:41–09:42", "Image rebuilt, converted to temperatures, mapped, measured and scored"],
                 ["About 09:42", "Climb Risk Score, advice and reasons on screen; countdown to the next pass (about 15:05 IST)"]],
                [0.22, 0.78], "Timeline of one pass. Times after the pass are estimates; the exact processing time depends on the computer.")]

    # ── 6 Study vs product ────────────────────────────────────
    s += [P("6. What the study proved, and what Meteor-M changes", "h1"),
          P("The research study tested SummitSathi's method on 1,425 archived <b>NOAA APT</b> passes over India. On a "
            "year it never saw (2019), it detected thunderstorms with an AUC of 0.90 against 0.81 for local weather "
            "history, and its Climb Risk bands matched reality. Moving to Meteor-M keeps the method but changes the "
            "input, so the steps divide into three groups:"),
          table([["Steps", "Status for Meteor-M", "What is needed"],
                 ["4.1 Pass prediction, 4.2 reception", "Standard; same principles as NOAA",
                  "Meteor-M orbital elements and frequencies"],
                 ["4.3–4.5 Demodulation, decoding, rebuilding",
                  "New for Meteor-M, but well established: open-source decoders do this routinely",
                  "Integration and testing on the device"],
                 ["4.6 Calibration, 4.7 map position", "Must be re-established",
                  "A temperature scale per satellite; coastline checks on Meteor-M images"],
                 ["4.8–4.10 Measurements, models, score", "Method carries over",
                  "Retrain and re-test the models on archived Meteor-M passes before quoting accuracy"]],
                [0.3, 0.36, 0.34], "Which parts of the product were proven in the study and which must be redone for Meteor-M."),
          P("<b>The honest position:</b> the accuracy figures in the study apply to NOAA APT data. The same pipeline, "
            "retrained on Meteor-M passes, is expected to do at least as well, because Meteor-M images are four times "
            "sharper (1 km against 4 km per pixel), carry an extra channel, and decode cleanly. But that has to be "
            "shown by repeating the test on Meteor-M data. SatNOGS also archives Meteor-M passes, so the same method "
            "used in the study can be applied.")]

    # ── 7 Limits ──────────────────────────────────────────────
    s += [P("7. Limits and safe use", "h1")]
    s += bullets([
        "<b>Snapshots, not a live feed.</b> Good passes come every five and a half to seven hours, so a storm can form "
        "between them. A <i>Stale</i> status means the view is old.",
        "<b>A view of the sky is needed.</b> Dense forest, deep valleys and buildings block the signal, especially "
        "for low passes.",
        "<b>Infrared sees cloud tops, not the ground.</b> Fog is detected only at night, and rain under thin cloud can be missed.",
        "<b>Orbit data ages.</b> Orbital elements should be refreshed every week or two for accurate pass timing.",
        "<b>A decision aid, not a guarantee.</b> In testing about 3 in 10 thunderstorms were missed, and many alerts "
        "were false alarms by design. SummitSathi supports a trekker's judgement; it does not replace it."])

    # ── 8 Glossary ────────────────────────────────────────────
    s += [P("8. Glossary", "h1"),
          table([["Term", "Meaning"],
                 ["APT", "Automatic Picture Transmission: the analogue image broadcast of the NOAA satellites, switched off in 2025"],
                 ["AUC", "How well a score ranks real hazards above calm moments; 0.5 is a coin toss, 1.0 is perfect"],
                 ["CCSDS", "The international standard for formatting and protecting spacecraft data"],
                 ["Doppler shift", "The change in received frequency caused by the satellite moving towards or away from you"],
                 ["I/Q samples", "Pairs of numbers from the radio describing a signal's strength and phase"],
                 ["LNA", "Low-noise amplifier: boosts a weak signal while adding as little noise as possible"],
                 ["LRPT", "Low Rate Picture Transmission: Meteor-M's digital, compressed image broadcast"],
                 ["MSU-MR", "The six-channel scanning camera on Meteor-M satellites"],
                 ["Overshooting top", "A very cold bump on a storm cloud where a strong updraft pushes through the top"],
                 ["QPSK", "A way of sending data by switching a radio wave between four phases, two bits per switch"],
                 ["Reed–Solomon", "An error-correcting code that repairs damaged bytes in a block of data"],
                 ["SDR", "Software-defined radio: a receiver whose tuning and decoding are done in software"],
                 ["SGP4", "The standard model for predicting a satellite's position from its orbital elements"],
                 ["Sun-synchronous orbit", "A polar orbit that passes over each place at about the same local times every day"],
                 ["TLE", "Two-line element set: the standard description of a satellite's current orbit"],
                 ["Viterbi decoding", "A method of correcting bit errors using the redundancy added by a convolutional code"]],
                [0.22, 0.78], None)]
    return s


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=20 * mm,
                          bottomMargin=18 * mm, title="How SummitSathi works", subject="Product guide, Meteor-M edition")
    frame = Frame(MARGIN, 18 * mm, TEXT_W, PAGE_H - 38 * mm, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(story())
    print(OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    build()
