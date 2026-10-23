#!/usr/bin/env python3
"""Build the eight-page reader's guide using only checked-in archive data.

Run from any directory:
    python scripts/build_pdf_guide.py

Requires reportlab and DejaVu Sans. No network access or source-data changes.
The per-route PDF builder is separate; this guide links to its stable outputs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
GITHUB = "https://github.com/Ding-Ding-Projects/go-bus-history-maps/blob/main/"
REPOSITORY = "https://github.com/Ding-Ding-Projects/go-bus-history-maps"
WIDTH, HEIGHT = letter
MARGIN = 42
CONTENT = WIDTH - 2 * MARGIN
PAGE_COUNT = 8

GREEN = colors.HexColor("#20664f")
TEXT = colors.HexColor("#16392e")
MUTED = colors.HexColor("#576b63")
PALE = colors.HexColor("#e8f1eb")
PAPER = colors.HexColor("#fcfdfb")
WATER = colors.HexColor("#e6f1f4")
LAND = colors.HexColor("#f5f2e9")
BORDER = colors.HexColor("#ccd9cf")
AMBER = colors.HexColor("#9a6320")
WHITE = colors.white


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def clean(text: object) -> str:
    return (
        str(text)
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", " - ")
        .replace("\u2212", "-")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u00a0", " ")
    )


def html(text: object) -> str:
    return escape(clean(text))


def date_text(value: str, year: bool = True) -> str:
    d = dt.date.fromisoformat(value)
    return f"{d.day} {d.strftime('%B')}" + (f" {d.year}" if year else "")


def short_date(value: str) -> str:
    d = dt.date.fromisoformat(value)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def link(label: str, destination: str) -> str:
    return f'<link href="{escape(destination, {chr(34): "&quot;"})}" color="#20664f"><u>{html(label)}</u></link>'


def register_fonts(directory: Path):
    fonts = {
        "Guide": "DejaVuSans.ttf",
        "Guide-Bold": "DejaVuSans-Bold.ttf",
        "Guide-Italic": "DejaVuSans-Oblique.ttf",
    }
    for name, filename in fonts.items():
        path = directory / filename
        if name == "Guide-Italic" and not path.exists():
            path = directory / "DejaVuSans.ttf"
        if not path.exists():
            raise SystemExit(f"Missing font: {path}. Use --font-dir to locate DejaVu Sans.")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "Guide", normal="Guide", bold="Guide-Bold", italic="Guide-Italic", boldItalic="Guide-Bold"
    )


class Guide:
    def __init__(self, output: Path):
        self.catalog = load("data/catalog.json")
        self.routes = sorted(self.catalog["routes"], key=lambda r: int(r["route"]))
        self.metadata = {s["id"]: s for s in load("data/snapshots.json")}
        self.land = load("assets/ontario-mainland.geojson")
        self.as_of = self.catalog["as_of"]
        self.snapshots = {}
        for sid in sorted(self.metadata):
            groups = []
            for route in self.routes:
                file = ROOT / "routes" / route["folder"] / "snapshots" / f"{sid}.json"
                if file.exists():
                    groups.append(json.loads(file.read_text(encoding="utf-8")))
            patterns = [p for group in groups for p in group["patterns"]]
            dates = sorted({d for p in patterns for d in p.get("service_dates", [])})
            self.snapshots[sid] = {
                "groups": groups,
                "patterns": patterns,
                "kinds": Counter(p["geometry_kind"] for p in patterns),
                "dates": dates,
            }
        points = [
            point
            for snapshot in self.snapshots.values()
            for p in snapshot["patterns"]
            for point in p.get("geometry", {}).get("coordinates", [])
        ]
        self.bounds = (
            min(p[0] for p in points) - 0.12,
            min(p[1] for p in points) - 0.07,
            max(p[0] for p in points) + 0.12,
            max(p[1] for p in points) + 0.07,
        )
        self.page = 0
        output.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(output), pagesize=letter, pageCompression=1, invariant=1)
        self.c.setTitle("GO Bus History Maps - Reader's Guide")
        self.c.setAuthor("Ding-Ding-Projects / GO Bus History Maps")
        self.c.setSubject(f"Documentary route archive guide - research edition {date_text(self.as_of)}")
        self.c.setKeywords("GO Transit, bus history, route maps, timetables, GTFS, Ontario")

    def para(self, text, x, y, width, size=10.5, leading=15, color=TEXT, bold=False):
        style = ParagraphStyle(
            "guide",
            fontName="Guide-Bold" if bold else "Guide",
            fontSize=size,
            leading=leading,
            textColor=color,
            alignment=TA_LEFT,
            spaceBefore=0,
            spaceAfter=0,
            allowWidows=0,
            allowOrphans=0,
        )
        p = Paragraph(text, style)
        _, height = p.wrap(width, HEIGHT)
        if y - height < 44:
            raise ValueError(f"Text exceeds content area on page {self.page}: {text[:90]}")
        p.drawOn(self.c, x, y - height)
        return y - height

    def text(self, value, x, y, size=10.5, color=TEXT, font="Guide", align="left"):
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        fn = {"left": self.c.drawString, "right": self.c.drawRightString, "center": self.c.drawCentredString}[align]
        fn(x, y, clean(value))

    def rule(self, x, y, width, color=BORDER, weight=0.6):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(weight)
        self.c.line(x, y, x + width, y)

    def page_start(self, key, title, kicker=None):
        self.page += 1
        self.c.setFillColor(PAPER)
        self.c.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        self.c.bookmarkPage(key)
        self.c.addOutlineEntry(title, key, level=0, closed=False)
        if kicker:
            self.text(kicker.upper(), MARGIN, 748, 8.6, GREEN, "Guide-Bold")
            self.text(title, MARGIN, 715, 25, TEXT, "Guide-Bold")

    def page_end(self):
        self.rule(MARGIN, 38, CONTENT)
        self.text("GO BUS HISTORY MAPS  |  " + date_text(self.as_of).upper(), MARGIN, 23, 7.8, MUTED)
        self.c.linkURL(REPOSITORY, (MARGIN, 18, MARGIN + 320, 34), relative=0, thickness=0)
        self.text(f"{self.page} / {PAGE_COUNT}", WIDTH - MARGIN, 22, 9, MUTED, align="right")
        self.c.showPage()

    def map(self, sid, x, y, width, height, cover=False):
        c = self.c
        c.saveState()
        c.setFillColor(WATER)
        c.roundRect(x, y, width, height, 7, fill=1, stroke=0)
        clip = c.beginPath()
        clip.rect(x, y, width, height)
        c.clipPath(clip, stroke=0, fill=0)
        lon0, lat0, lon1, lat1 = self.bounds
        cosine = math.cos(math.radians((lat0 + lat1) / 2))
        scale = min((width - 16) / ((lon1 - lon0) * cosine), (height - 18) / (lat1 - lat0))
        ox = x + (width - (lon1 - lon0) * cosine * scale) / 2
        oy = y + (height - (lat1 - lat0) * scale) / 2

        def project(lon, lat):
            return ox + (lon - lon0) * cosine * scale, oy + (lat - lat0) * scale

        c.setFillColor(LAND)
        c.setStrokeColor(colors.HexColor("#d6d9ce"))
        c.setLineWidth(0.25)
        for feature in self.land["features"]:
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            for polygon in polygons:
                path = c.beginPath()
                for ring in polygon:
                    if not ring:
                        continue
                    sx, sy = project(*ring[0])
                    path.moveTo(sx, sy)
                    for point in ring[1:]:
                        path.lineTo(*project(*point))
                    path.close()
                c.drawPath(path, stroke=1, fill=1, fillMode=0)

        # Draw each unique source geometry once at this scale. Directional pattern
        # counts are still reported separately; duplicated lines are not frequency.
        seen = set()
        patterns = sorted(self.snapshots[sid]["patterns"], key=lambda p: p["geometry_kind"] == "stop-connections")
        for p in patterns:
            geometry = p.get("geometry", {})
            if geometry.get("type") != "LineString":
                continue
            coords = geometry.get("coordinates", [])
            if len(coords) < 2:
                continue
            encoded = tuple(tuple(point) for point in coords)
            key = min(encoded, tuple(reversed(encoded)))
            if key in seen:
                continue
            seen.add(key)
            c.setStrokeColor(GREEN)
            schematic = p["geometry_kind"] == "stop-connections"
            c.setStrokeAlpha(0.52 if schematic else 0.70)
            c.setLineWidth(0.85 if cover else 0.60)
            c.setDash(2.2, 2.0) if schematic else c.setDash()
            path = c.beginPath()
            path.moveTo(*project(*coords[0]))
            for point in coords[1:]:
                path.lineTo(*project(*point))
            c.drawPath(path, fill=0, stroke=1)
        c.setDash()
        c.setStrokeAlpha(1)
        stops = {}
        for group in self.snapshots[sid]["groups"]:
            for p in group["patterns"]:
                for s in p["stops"]:
                    stops.setdefault(s["name"], s)
        anchors = [
            ("Stratford", ["Stratford GO Bus"], 5, 7),
            ("Waterloo", ["University of Waterloo Terminal", "University of Waterloo"], -5, 8),
            ("Hamilton", ["Hamilton GO Centre Bus"], -8, -13),
            ("Toronto", ["Union Station Bus Terminal"], 6, -13),
            ("Oshawa", ["Oshawa GO Bus", "Durham College Oshawa GO", "Oshawa GO"], 6, -10),
            ("Barrie", ["Barrie Transit Terminal", "Allandale Waterfront GO Bus", "Allandale Waterfront GO"], 5, 8),
            ("Peterborough", ["Peterborough Bus Terminal"], -5, 8),
            ("Niagara Falls", ["Niagara Falls Bus Terminal"], 6, -10),
        ]
        label_size = 9.2 if cover else 7.8
        for name, alternatives, dx, dy in anchors:
            stop = next((stops[n] for n in alternatives if n in stops), None)
            if stop is None:
                continue
            px, py = project(stop["lon"], stop["lat"])
            c.setFillColor(WHITE)
            c.setStrokeColor(GREEN)
            c.setLineWidth(0.75)
            c.circle(px, py, 2.1 if cover else 1.6, fill=1, stroke=1)
            tw = pdfmetrics.stringWidth(name, "Guide-Bold", label_size)
            tx = px + dx if dx >= 0 else px + dx - tw
            tx = max(x + 5, min(tx, x + width - tw - 5))
            ty = max(y + 31, min(py + dy, y + height - 13))
            c.setFillColor(WHITE)
            c.setFillAlpha(0.88)
            c.roundRect(tx - 2, ty - 2, tw + 4, label_size + 4, 2, fill=1, stroke=0)
            c.setFillAlpha(1)
            self.text(name, tx, ty, label_size, TEXT, "Guide-Bold")

        # A label in an otherwise unfilled area; the backdrop is only Ontario's
        # published mainland layer and does not purport to map neighbouring land.
        lx, ly = project(-79.20, 43.44)
        self.text("LAKE ONTARIO", lx, ly, 9.5 if cover else 8.0, colors.HexColor("#638794"), "Guide-Italic", "center")
        nx, ny = x + width - 17, y + height - 18
        self.text("N", nx, ny, 8, MUTED, "Guide-Bold", "center")
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.65)
        c.line(nx, ny - 14, nx, ny - 3)
        c.line(nx, ny - 3, nx - 2, ny - 6)
        c.line(nx, ny - 3, nx + 2, ny - 6)
        distance = 50 / 111.32 * scale
        c.setFillColor(WHITE)
        c.setFillAlpha(0.88)
        c.roundRect(x + 7, y + 6, distance + 19, 22, 3, fill=1, stroke=0)
        c.setFillAlpha(1)
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.8)
        c.line(x + 13, y + 16, x + 13 + distance, y + 16)
        c.line(x + 13, y + 14, x + 13, y + 18)
        c.line(x + 13 + distance, y + 14, x + 13 + distance, y + 18)
        self.text("50 km approx.", x + 13, y + 8, 6.7, MUTED)
        c.restoreState()
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.7)
        c.roundRect(x, y, width, height, 7, fill=0, stroke=1)

    def cover(self):
        self.page_start("cover", "Start here")
        self.text("A DOCUMENTARY ARCHIVE", 36, 748, 9, GREEN, "Guide-Bold")
        self.text("GO BUS", 36, 699, 42, TEXT, "Guide-Bold")
        self.text("HISTORY MAPS", 36, 652, 42, TEXT, "Guide-Bold")
        self.text("A reader's guide to routes, dates and evidence", 36, 622, 14, GREEN)
        self.para(
            "Find a route, compare the surviving maps, and follow its ordered stops back to the original sources.",
            36, 602, 540, 10.8, 15, MUTED,
        )
        self.map(self.as_of, 36, 209, 540, 354, cover=True)
        self.para(
            f"<b>Latest captured network:</b> {date_text(self.as_of)}. Lines combine the patterns in that feed; they are not a map of simultaneous departures. Ontario mainland reference backdrop.",
            36, 196, 540, 9.2, 12.5, MUTED,
        )
        metrics = [
            (str(len(self.routes)), "numbered families"),
            (str(len(self.snapshots)), "original feed captures"),
            (f"{self.catalog['pattern_count']:,}", "documented patterns"),
            (str(len(self.catalog["legacy"])), "named legacy corridors"),
        ]
        for i, (number, label) in enumerate(metrics):
            x = 36 + i * 138
            self.c.setFillColor(PALE)
            self.c.roundRect(x, 91, 126, 65, 6, fill=1, stroke=0)
            self.text(number, x + 12, 123, 24, GREEN, "Guide-Bold")
            self.para(html(label), x + 12, 112, 105, 8.8, 11, MUTED)
        self.text("RESEARCH EDITION  " + date_text(self.as_of).upper(), 36, 66, 9, MUTED, "Guide-Bold")
        self.c.linkRect("Read the guide", "reading", (36, 209, 576, 563), relative=0, thickness=0)
        self.page_end()

    def reading_page(self):
        self.page_start("reading", "How to read this archive", "Start with the evidence")
        y = self.para(
            "Choose a route in the numeric index, then open its PDF. Each route brings together a sourced history, dated maps and the stop order behind each documented version.",
            MARGIN, 690, CONTENT,
        ) - 21
        self.text("Three kinds of route line", MARGIN, y, 14, TEXT, "Guide-Bold")
        y -= 24
        examples = [
            ("Original feed geometry", "A line supplied in a GO operating-data feed. Some lines are clipped to the trip's first and last stops; detail is simplified for display.", False),
            ("Reconstructed historical corridor", "A research reconstruction, identified in the caption. It may use modern road references and generalized terminal approaches.", False),
            ("Schematic stop connections", "A dashed line preserves the known stop order. It does not establish which roads the bus used between those points.", True),
        ]
        for title, description, dashed in examples:
            self.c.setStrokeColor(GREEN)
            self.c.setLineWidth(2)
            self.c.setDash(5, 3) if dashed else self.c.setDash()
            self.c.line(MARGIN, y - 9, MARGIN + 62, y - 9)
            self.c.setDash()
            for px in [MARGIN + 5, MARGIN + 57]:
                self.c.setFillColor(WHITE)
                self.c.circle(px, y - 9, 3, stroke=1, fill=1)
            self.text(title, MARGIN + 80, y, 10.8, TEXT, "Guide-Bold")
            bottom = self.para(html(description), MARGIN + 80, y - 9, CONTENT - 80, 10.2, 14.2, MUTED)
            y = bottom - 22
        self.c.setLineWidth(0.6)
        self.c.setFillColor(PALE)
        self.c.roundRect(MARGIN, y - 59, CONTENT, 63, 6, fill=1, stroke=0)
        self.para(
            "<b>Read the caption and location notes.</b> A solid reconstructed line is not original operating geometry. A station or junction marker may be a reference area from another year; it does not certify an old bus bay.",
            MARGIN + 13, y - 7, CONTENT - 26, 10.2, 14,
        )
        y -= 86
        self.text("Dates answer different questions", MARGIN, y, 14, TEXT, "Guide-Bold")
        y -= 22
        for label, detail in [
            ("Capture date", "When a feed was archived or downloaded. Its service calendar can begin earlier or extend later."),
            ("Effective date", "The stated start date in a timetable or service-change notice."),
            ('"By" a date', "A surviving source establishes that the service existed by then; its precise introduction date may remain unknown."),
        ]:
            self.text(label, MARGIN, y - 1, 10.3, GREEN, "Guide-Bold")
            bottom = self.para(html(detail), MARGIN + 106, y + 8, CONTENT - 106, 10.2, 14)
            y = bottom - 15
        y -= 1
        self.rule(MARGIN, y, CONTENT)
        y -= 24
        self.text("Where to go next", MARGIN, y, 14, TEXT, "Guide-Bold")
        y -= 22
        for title, pages, key in [
            ("Four captured networks", "pages 3-4", "networks-early"),
            ("Routes in numeric order", "pages 5-7", "index-1"),
            ("Named legacy services, sources and limits", "page 8", "sources"),
        ]:
            self.text(title, MARGIN, y, 10.4, GREEN)
            self.text(pages, WIDTH - MARGIN, y, 10.1, MUTED, align="right")
            self.c.linkRect(title, key, (MARGIN, y - 4, WIDTH - MARGIN, y + 13), relative=0, thickness=0)
            y -= 22
        self.page_end()

    def network_panel(self, sid, y):
        snapshot = self.snapshots[sid]
        self.map(sid, MARGIN, y, 357, 258)
        x = MARGIN + 375
        width = CONTENT - 375
        year = sid[:4]
        self.text(year, x, y + 234, 29, GREEN, "Guide-Bold")
        self.text(date_text(sid, year=False), x, y + 214, 11, TEXT)
        self.text("FEED CAPTURE", x, y + 196, 7.9, MUTED, "Guide-Bold")
        self.rule(x, y + 181, width)
        self.text(f"{len(snapshot['groups'])} route families", x, y + 163, 11, TEXT, "Guide-Bold")
        self.text(f"{len(snapshot['patterns']):,} directional patterns", x, y + 146, 9.2, MUTED)
        self.text("Service dates represented", x, y + 122, 8.3, MUTED, "Guide-Bold")
        d1, d2 = snapshot["dates"][0], snapshot["dates"][-1]
        self.para(f"{html(short_date(d1))}<br/>to {html(short_date(d2))}", x, y + 110, width, 10, 14)
        schematic = snapshot["kinds"].get("stop-connections", 0)
        shape_count = len(snapshot["patterns"]) - schematic
        self.para(
            f"<b>{shape_count}</b> use supplied geometry<br/><b>{schematic}</b> use schematic connections",
            x, y + 70, width, 9.1, 13.5, MUTED,
        )
        self.para(link("Source feed and metadata", GITHUB + "data/snapshots.json"), x, y + 25, width, 8.5, 11.5)

    def networks_page(self, sids, key, title):
        self.page_start(key, title, "Four snapshots, not a continuous record")
        self.para(
            "The maps share the same extent and scale. Each combines every pattern contained in that captured feed, including trips scheduled on different dates.",
            MARGIN, 690, CONTENT, 10.5, 15,
        )
        self.c.setStrokeColor(GREEN)
        self.c.setLineWidth(1.5)
        self.c.line(MARGIN, 644, MARGIN + 22, 644)
        self.text("Supplied geometry", MARGIN + 29, 640, 8.7, MUTED)
        self.c.setDash(3, 2)
        self.c.line(MARGIN + 164, 644, MARGIN + 186, 644)
        self.c.setDash()
        self.text("Schematic connections", MARGIN + 193, 640, 8.7, MUTED)
        self.network_panel(sids[0], 365)
        self.network_panel(sids[1], 86)
        self.para(
            "Counts reflect documented directions, branches, restrictions and source geometry - not service frequency. Modern Ontario mainland is reference geography; source detail is shown at overview scale.",
            MARGIN, 73, CONTENT, 8.5, 11, MUTED,
        )
        self.page_end()

    def index_page(self, routes, number):
        first, last = routes[0]["route"], routes[-1]["route"]
        self.page_start(f"index-{number}", f"Route index: {first}-{last}", "Select a route to open its PDF on GitHub")
        self.para(
            "Patterns combine all captured directions and documented historical versions. A reused number can represent different services in different eras.",
            MARGIN, 690, CONTENT, 10.2, 14.5,
        )
        columns = [MARGIN, MARGIN + 44, MARGIN + 376, MARGIN + 468]
        y = 643
        self.c.setFillColor(GREEN)
        self.c.roundRect(MARGIN, y - 23, CONTENT, 26, 4, fill=1, stroke=0)
        self.text("ROUTE", columns[0] + 5, y - 13, 8.0, WHITE, "Guide-Bold")
        self.text("SERVICE FAMILY / ERAS", columns[1] + 4, y - 13, 8.0, WHITE, "Guide-Bold")
        self.text("STATUS", columns[2] + 4, y - 13, 8.0, WHITE, "Guide-Bold")
        self.text("PATTERNS", WIDTH - MARGIN - 7, y - 13, 8.0, WHITE, "Guide-Bold", "right")
        y -= 23
        style = ParagraphStyle("index", fontName="Guide", fontSize=10, leading=12.7, textColor=TEXT)
        for i, route in enumerate(routes):
            p = Paragraph(html(route["name"]), style)
            _, h = p.wrap(322, 100)
            row_h = max(23, h + 10)
            if y - row_h < 100:
                raise ValueError(f"Route index overflow: {route['route']}")
            if i % 2 == 0:
                self.c.setFillColor(colors.HexColor("#f0f5f0"))
                self.c.rect(MARGIN, y - row_h, CONTENT, row_h, fill=1, stroke=0)
            self.c.setFillColor(PALE)
            self.c.roundRect(MARGIN + 5, y - row_h / 2 - 9, 29, 18, 4, fill=1, stroke=0)
            self.text(route["route"], MARGIN + 19.5, y - row_h / 2 - 3.4, 10.6, GREEN, "Guide-Bold", "center")
            p.drawOn(self.c, columns[1] + 4, y - (row_h + h) / 2)
            status = route["status"].capitalize()
            sc = GREEN if status == "Current" else AMBER if status == "Special" else MUTED
            self.text(status, columns[2] + 4, y - row_h / 2 - 3.1, 8.6, sc)
            self.text(str(route["pattern_count"]), WIDTH - MARGIN - 13, y - row_h / 2 - 3.5, 10.5, TEXT, "Guide-Bold", "right")
            destination = GITHUB + f"routes/{route['folder']}/route-{route['folder']}-history.pdf"
            self.c.linkURL(destination, (MARGIN, y - row_h, WIDTH - MARGIN, y), relative=0, thickness=0)
            self.rule(MARGIN, y - row_h, CONTENT, BORDER, 0.35)
            y -= row_h
        y -= 17
        self.para(
            '<b>Current</b> means present in the latest captured feed. <b>Special</b> includes replacement service. Check the recorded service dates; neither status means a bus runs every day.',
            MARGIN, y, CONTENT, 9.1, 13, MUTED,
        )
        self.para(
            link("Catalog and route coverage", GITHUB + "docs/COVERAGE.md") + " &nbsp; | &nbsp; " + link("Named legacy services", GITHUB + "legacy/README.md"),
            MARGIN, 70, CONTENT, 9, 12,
        )
        self.page_end()

    def sources_page(self):
        self.page_start("sources", "Legacy services & source notes", "Keep names, route numbers and evidence separate")
        self.para(
            "Some older timetables used table identifiers that are not evidence of a public route number. These named corridors are therefore filed separately.",
            MARGIN, 690, CONTENT, 10.5, 15,
        )
        y = 642
        for i, record in enumerate(self.catalog["legacy"]):
            x = MARGIN + i * 273
            width = 255
            self.c.setFillColor(PALE)
            self.c.roundRect(x, y - 83, width, 83, 6, fill=1, stroke=0)
            short = "Bayview GO Bus Service" if record["id"] == "bayview" else "Yonge C / North Yonge Local"
            self.para(html(short), x + 13, y - 11, width - 26, 11, 15, TEXT, True)
            self.text(f"{record['patterns']} documented versions", x + 13, y - 45, 10, MUTED)
            self.para(link("Open the illustrated PDF", GITHUB + f"legacy/{record['id']}/{record['id']}-history.pdf"), x + 13, y - 57, width - 26, 10, 13)
        y -= 108
        self.text("Follow the evidence", MARGIN, y, 14, TEXT, "Guide-Bold")
        y -= 21
        source_rows = [
            (
                "Original operating data",
                "The four GO / Metrolinx feeds supply branch labels, ordered stops, geometry and service dates. "
                + link("Captures, feed metadata and checksums", GITHUB + "data/snapshots.json") + ".",
            ),
            (
                "Timetables and service changes",
                "Route histories cite the actual original timetables, operator notices and labeled secondary reporting. "
                + link("Full source directory", GITHUB + "docs/SOURCES.md") + ".",
            ),
            (
                "Discovery catalog",
                f"The archive indexes {self.catalog['archive_document_count']:,} timetable links. An indexed link is not a claim that the document was reviewed or that its table number proves a route. "
                + link("Timetable catalog", GITHUB + "data/schedule-archive.json") + ".",
            ),
        ]
        for title, description in source_rows:
            self.text(title, MARGIN, y, 10.6, GREEN, "Guide-Bold")
            bottom = self.para(description, MARGIN, y - 9, CONTENT, 10.1, 14)
            y = bottom - 18
        self.text("What the surviving record does not establish", MARGIN, y, 14, TEXT, "Guide-Bold")
        y -= 21
        y = self.para(
            "The collection is documentary, not an unbroken history of every trip since GO bus service began. Missing intermediate timetables, temporary diversions and unprinted roadside stops remain research gaps. Manual patterns often preserve major timing points rather than every stop.<br/><br/>"
            "Unknown locations remain in the correct stop order. Reference coordinates and modern road geography do not prove an exact historical platform, roadway or municipal boundary. "
            + link("Methodology and location notes", GITHUB + "docs/METHODOLOGY.md") + ".",
            MARGIN, y, CONTENT, 10.1, 14,
        ) - 19
        self.rule(MARGIN, y, CONTENT)
        y -= 19
        self.text("DATA PERMISSION & GEOGRAPHIC CREDIT", MARGIN, y, 8.3, MUTED, "Guide-Bold")
        y -= 11
        y = self.para(
            "Data used in this product or service is provided with the permission of Metrolinx. Metrolinx makes no representations or warranties of any kind, express or implied, with respect to the Data and assumes no responsibility for the accuracy or currency of the data used in this product or service.",
            MARGIN, y, CONTENT, 8.9, 12.4, MUTED,
        ) - 9
        y = self.para(
            "Ontario mainland boundaries: Ontario Ministry of Natural Resources, Open Government Licence - Ontario. Selected historical reference geometry: OpenStreetMap contributors, ODbL 1.0. "
            + link("Credits and original-data terms", GITHUB + "docs/SOURCES.md") + ".",
            MARGIN, y, CONTENT, 8.9, 12.4, MUTED,
        ) - 9
        self.para(
            "An independent history project. For present-day journeys, consult official GO Transit schedules.",
            MARGIN, y, CONTENT, 9.3, 13, GREEN,
        )
        self.page_end()

    def build(self):
        if len(self.routes) != 60 or len(self.snapshots) != 4:
            raise ValueError("The fixed eight-page layout expects this edition's 60 route families and four captures.")
        self.cover()
        self.reading_page()
        self.networks_page(["2016-01-11", "2022-03-08"], "networks-early", "The network in 2016 and 2022")
        self.networks_page(["2023-05-05", "2026-10-23"], "networks-recent", "The network in 2023 and 2026")
        for number, offset in enumerate(range(0, len(self.routes), 20), 1):
            self.index_page(self.routes[offset : offset + 20], number)
        self.sources_page()
        assert self.page == PAGE_COUNT
        self.c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "pdfs" / "GO-Bus-History-Guide.pdf")
    parser.add_argument("--font-dir", type=Path, default=Path("/usr/share/fonts/truetype/dejavu"))
    args = parser.parse_args()
    register_fonts(args.font_dir)
    guide = Guide(args.output)
    guide.build()
    print(f"Created {args.output} ({PAGE_COUNT} pages; {args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
