#!/usr/bin/env python3
"""Generate the homepage's geographic SVG and an original transit favicon.

Only checked-in operating geometry and Ontario reference geography are used.
Run: python scripts/build_web_graphics.py
No external packages or network access are required.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
COSINE = math.cos(math.radians(43.7))
IVORY = "#f6f3e9"
FOREST = "#20664f"
INK = "#16392e"
MUTED = "#63766a"
AMBER = "#ad7d38"
WATER = "#e9efeb"
LAND = "#f8f5ec"
LINE = "#d9dfd0"
MAIN_BOUNDS = (-80.20, 43.15, -78.15, 44.11)
MAIN_FRAME = (0, 0, 1440, 930)
INSET_FRAME = (1040, 660, 356, 217)
DISPLAY_TOLERANCE = 0.00020  # about 22 metres; well below one main-view pixel


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def project(point):
    return point[0] * COSINE, -point[1]


def distance_to_segment_squared(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return (p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2


def simplify(points, tolerance=DISPLAY_TOLERANCE):
    """Iterative Douglas-Peucker simplification in the display projection."""
    if len(points) < 3:
        return points
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    threshold = tolerance * tolerance
    while pending:
        first, last = pending.pop()
        if last - first < 2:
            continue
        distance, index = max(
            (distance_to_segment_squared(points[i], points[first], points[last]), i)
            for i in range(first + 1, last)
        )
        if distance > threshold:
            keep.add(index)
            pending.extend(((first, index), (index, last)))
    return [points[i] for i in sorted(keep)]


def path_from_points(points, closed=False):
    if not points:
        return ""
    return "M" + "L".join(f"{x:.6f},{y:.6f}" for x, y in points) + ("Z" if closed else "")


def transform(bounds, frame):
    lon0, lat0, lon1, lat1 = bounds
    left, top = project((lon0, lat1))
    right, bottom = project((lon1, lat0))
    x, y, width, height = frame
    scale = min(width / (right - left), height / (bottom - top))
    ox = x + (width - (right - left) * scale) / 2 - left * scale
    oy = y + (height - (bottom - top) * scale) / 2 - top * scale
    return scale, ox, oy


def pixel(point, matrix):
    px, py = project(point)
    scale, ox, oy = matrix
    return px * scale + ox, py * scale + oy


def date_string(value, long=False):
    d = dt.date.fromisoformat(value)
    return f"{d.day} {d.strftime('%B' if long else '%b')} {d.year}"


def text(value, x, y, size=26, fill=INK, weight=600, anchor="start", extra=""):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(value)}</text>'


def map_use(matrix, clip, main=True):
    scale, ox, oy = matrix
    route_width = (3.1 if main else 1.25) / scale
    border_width = (0.75 if main else 0.45) / scale
    return f'''
      <g clip-path="url(#{clip})">
        <g transform="matrix({scale:.6f} 0 0 {scale:.6f} {ox:.6f} {oy:.6f})">
          <use href="#ontario-mainland" xlink:href="#ontario-mainland" fill="{LAND}" stroke="{LINE}" stroke-width="{border_width:.8f}"/>
          <use href="#captured-routes" xlink:href="#captured-routes" fill="none" stroke="{FOREST}" stroke-width="{route_width:.8f}" stroke-linejoin="round" stroke-linecap="round"/>
          <use href="#schematic-routes" xlink:href="#schematic-routes" fill="none" stroke="{FOREST}" stroke-width="{route_width:.8f}" stroke-dasharray="{5 / scale:.8f} {4 / scale:.8f}" stroke-linejoin="round" stroke-linecap="round"/>
        </g>
      </g>'''


def main():
    catalog = read("data/catalog.json")
    captures = read("data/snapshots.json")
    latest = max(captures, key=lambda item: item["id"])
    sid = latest["id"]
    snapshots = []
    for route in sorted(catalog["routes"], key=lambda item: int(item["route"])):
        path = ROOT / "routes" / route["folder"] / "snapshots" / f"{sid}.json"
        if path.exists():
            snapshots.append(json.loads(path.read_text(encoding="utf-8")))
    patterns = [p for snapshot in snapshots for p in snapshot["patterns"]]
    active_dates = sorted({d for p in patterns for d in p.get("service_dates", [])})
    all_points = [point for p in patterns for point in p["geometry"]["coordinates"]]
    stops = {}
    for p in patterns:
        for s in p["stops"]:
            stops.setdefault(s["name"], s)
    land = read("assets/ontario-mainland.geojson")
    land_paths = []
    for feature in land["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            land_paths.append("".join(path_from_points([project(p) for p in ring], True) for ring in polygon))

    seen = set()
    paths = {"source": [], "schematic": []}
    display_vertices = 0
    for pattern in patterns:
        geometry = pattern["geometry"]
        if geometry["type"] != "LineString":
            raise ValueError(f"Unexpected geometry type: {pattern['id']}")
        points = simplify([project(p) for p in geometry["coordinates"]])
        coords = tuple((round(p[0], 6), round(p[1], 6)) for p in points)
        key = min(coords, tuple(reversed(coords)))
        if key in seen:
            continue
        seen.add(key)
        display_vertices += len(points)
        kind = "schematic" if pattern["geometry_kind"] == "stop-connections" else "source"
        paths[kind].append(path_from_points(points))

    whole_bounds = (
        min(min(p[0] for p in all_points), MAIN_BOUNDS[0]) - 0.10,
        min(min(p[1] for p in all_points), MAIN_BOUNDS[1]) - 0.07,
        max(max(p[0] for p in all_points), MAIN_BOUNDS[2]) + 0.07,
        max(max(p[1] for p in all_points), MAIN_BOUNDS[3]) + 0.07,
    )
    main_matrix = transform(MAIN_BOUNDS, MAIN_FRAME)
    inset_matrix = transform(whole_bounds, INSET_FRAME)
    required_legend = (
        "Data used in this product or service is provided with the permission of Metrolinx. "
        "Metrolinx makes no representations or warranties of any kind, express or implied, with respect to the Data "
        "and assumes no responsibility for the accuracy or currency of the data used in this product or service."
    )
    metadata = {
        "title": "GO bus network overview",
        "capture_date": sid,
        "service_dates_represented": [active_dates[0], active_dates[-1]],
        "route_families": len(snapshots),
        "directional_patterns": len(patterns),
        "meaning": "All patterns in one captured feed; not simultaneous departures, frequency, or a mixture of historical networks.",
        "operating_geometry_source": latest["url"],
        "original_feed_sha256": latest["sha256"],
        "checked_in_source": f"routes/*/snapshots/{sid}.json",
        "geometry_note": "Supplied GO shapes and source-shape clipping are inherited from the archive. About 22 m display simplification is applied only in this SVG.",
        "projection": "Local equirectangular display with longitude scaled by cosine of 43.7 degrees north.",
        "labels": "Selected source-GTFS stop coordinates; label offsets are purely typographic.",
        "main_view_bounds_wgs84": MAIN_BOUNDS,
        "whole_network_bounds_wgs84": whole_bounds,
        "geography": read("data/basemap-source.json"),
        "geography_credit": "Ontario Ministry of Natural Resources, Open Government Licence - Ontario. Modern mainland reference geography only.",
        "metrolinx_legend": required_legend,
        "project": "https://github.com/Ding-Ding-Projects/go-bus-history-maps",
    }
    pieces = [f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1440 1000" width="1440" height="1000" role="img" aria-labelledby="network-title network-description">
      <title id="network-title">GO bus network, captured {date_string(sid, True)}</title>
      <desc id="network-description">A geographic view of the Greater Toronto and Hamilton Area, with a smaller inset showing the full captured GO bus network. Dark green lines are operating-data geometry. Amber-centred markers identify selected reference hubs. The inset outline shows the main view. All {len(patterns)} directional patterns in the {sid} feed are combined; they were not all scheduled to run simultaneously. Service dates represented: {active_dates[0]} through {active_dates[-1]}. The backdrop is modern Ontario mainland geography.</desc>
      <metadata>{escape(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))}</metadata>
      <defs>
        <clipPath id="main-clip"><rect x="0" y="0" width="1440" height="930" rx="24"/></clipPath>
        <clipPath id="inset-clip"><rect x="1040" y="660" width="356" height="217" rx="6"/></clipPath>
        <g id="ontario-mainland" fill-rule="evenodd">''']
    pieces.extend(f'<path d="{p}"/>' for p in land_paths)
    pieces.extend([
        '</g>',
        f'<path id="captured-routes" d="{"".join(paths["source"])}"/>',
        f'<path id="schematic-routes" d="{"".join(paths["schematic"])}"/>',
        '</defs>',
        f'<g font-family="DejaVu Sans,Arial,sans-serif"><rect width="1440" height="1000" fill="{IVORY}"/>',
        f'<rect width="1440" height="930" rx="24" fill="{WATER}"/>',
        map_use(main_matrix, "main-clip"),
    ])

    # Geographic hubs are selected only by exact checked-in GTFS names.
    labels = [
        ("Newmarket", "Davis Dr. @ Superior St. (Newmarket GO)", 0, -20, "middle", 27),
        ("Richmond Hill Centre", "Richmond Hill Centre", 22, -31, "start", 26),
        ("Highway 407", "Hwy 407 Bus Terminal", -28, -21, "end", 28),
        ("Bramalea", "Bramalea GO Bus", -23, -22, "end", 26),
        ("Pearson T1", "Pearson Airport Terminal 1", 24, -7, "start", 25),
        ("Square One", "Square One", -26, 37, "end", 27),
        ("Union Station", "Union Station Bus Terminal", 24, 24, "start", 28),
        ("Unionville", "Unionville GO Bus", 28, 34, "start", 25),
        ("Oshawa GO", "Durham College Oshawa GO", 25, -14, "start", 28),
        ("Oakville", "Oakville GO Bus", 23, 22, "start", 27),
        ("Burlington", "Burlington GO Bus", 24, 14, "start", 26),
        ("Hamilton", "Hamilton GO Centre Bus", -24, -9, "end", 28),
    ]
    for label, source_name, dx, dy, anchor, size in labels:
        if source_name not in stops:
            raise ValueError(f"Missing exact label source: {source_name}")
        stop = stops[source_name]
        px, py = pixel((stop["lon"], stop["lat"]), main_matrix)
        if not (0 < px < 1440 and 0 < py < 930):
            raise ValueError(f"Selected hub falls outside the main view: {label}")
        pieces.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="11" fill="{IVORY}" opacity="0.84"/>')
        pieces.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6.5" fill="{IVORY}" stroke="{FOREST}" stroke-width="2.2"/>')
        pieces.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.8" fill="{AMBER}"/>')
        label_extra = f'stroke="{LAND}" stroke-width="7" paint-order="stroke" stroke-linejoin="round"'
        pieces.append(text(label, px + dx, py + dy, size, INK, 600, anchor, label_extra))

    pieces.append(text("LAKE ONTARIO", 1030, 505, 30, "#879b91", 400, "middle", 'letter-spacing="5"'))
    pieces.append(text("N", 1384, 55, 21, MUTED, 600, "middle"))
    pieces.append(f'<path d="M1384 103V66M1377 76L1384 66L1391 76" fill="none" stroke="{MUTED}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')
    # Scale bar in the main projection, stated approximately for a regional view.
    length = 20 / 111.32 * main_matrix[0]
    pieces.append(f'<g fill="none" stroke="{MUTED}" stroke-width="1.8"><path d="M42 887H{42+length:.2f}M42 882V892M{42+length:.2f} 882V892"/></g>')
    pieces.append(text("20 km approx.", 42, 915, 17, MUTED, 400))

    # The inset is a complete view of the same feed, not an additional era.
    pieces.append(f'<rect x="1030" y="626" width="380" height="283" rx="14" fill="{INK}" opacity="0.07"/>')
    pieces.append(f'<rect x="1028" y="622" width="380" height="283" rx="14" fill="{IVORY}" stroke="#cbd5c7" stroke-width="1.4"/>')
    pieces.append(text("WHOLE-NETWORK CONTEXT", 1048, 649, 17, MUTED, 600, extra='letter-spacing="1"'))
    pieces.append(f'<rect x="1040" y="660" width="356" height="217" rx="6" fill="{WATER}"/>')
    pieces.append(map_use(inset_matrix, "inset-clip", main=False))
    vx0, vy0 = pixel((MAIN_BOUNDS[0], MAIN_BOUNDS[3]), inset_matrix)
    vx1, vy1 = pixel((MAIN_BOUNDS[2], MAIN_BOUNDS[1]), inset_matrix)
    pieces.append(f'<rect x="{vx0:.2f}" y="{vy0:.2f}" width="{vx1-vx0:.2f}" height="{vy1-vy0:.2f}" fill="{AMBER}" fill-opacity="0.035" stroke="{AMBER}" stroke-width="1.4" stroke-dasharray="5 4" clip-path="url(#inset-clip)"/>')
    for label, alternatives, dx, dy, anchor in [
        ("Stratford", ["Stratford GO Bus"], 4, -6, "start"),
        ("Barrie", ["Allandale Waterfront GO Bus"], -6, 17, "end"),
        ("Peterborough", ["Peterborough Bus Terminal"], -4, -5, "end"),
        ("Niagara Falls", ["Niagara Falls Bus Terminal"], 4, 15, "start"),
    ]:
        stop = next((stops[n] for n in alternatives if n in stops), None)
        if not stop:
            continue
        px, py = pixel((stop["lon"], stop["lat"]), inset_matrix)
        pieces.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2" fill="{FOREST}"/>')
        pieces.append(text(label, px + dx, py + dy, 13, MUTED, 600, anchor, f'stroke="{LAND}" stroke-width="3" paint-order="stroke"'))
    pieces.append(f'<rect x="1049" y="886" width="12" height="8" fill="none" stroke="{AMBER}" stroke-width="1.4"/>')
    pieces.append(text("Outline shows main view", 1069, 894, 13.8, MUTED, 400))
    pieces.append(f'<rect width="1440" height="930" rx="24" fill="none" stroke="#dbe1d4" stroke-width="1.3"/>')

    # Small atlas caption; the homepage supplies the editorial heading.
    pieces.append(text(date_string(sid).upper() + " CAPTURE", 32, 962, 20, FOREST, 600, extra='letter-spacing="0.8"'))
    pieces.append(f'<path d="M391 954H433" stroke="{FOREST}" stroke-width="3" stroke-linecap="round"/>')
    pieces.append(text("Captured bus geometry", 447, 962, 18, MUTED, 400))
    pieces.append(f'<circle cx="716" cy="954" r="5.8" fill="{IVORY}" stroke="{FOREST}" stroke-width="1.8"/><circle cx="716" cy="954" r="2.4" fill="{AMBER}"/>')
    pieces.append(text("Selected hubs", 732, 962, 18, MUTED, 400))
    pieces.append(text("Not simultaneous departures", 1408, 962, 17, MUTED, 400, "end"))
    pieces.append(text(f"Service dates: {date_string(active_dates[0])} to {date_string(active_dates[-1])}. All patterns combined.", 32, 988, 15.5, MUTED, 400))
    pieces.append(text("GO / Metrolinx data · Ontario mainland reference", 1408, 988, 15.5, MUTED, 400, "end"))
    pieces.append('</g></svg>')
    target = ASSETS / "network-overview.svg"
    target.write_text("\n".join(pieces) + "\n", encoding="utf-8")

    favicon = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" role="img" aria-labelledby="favicon-title">
      <title id="favicon-title">GO Bus History Maps - original route-line symbol</title>
      <desc>An original abstract transit route with three stops. It does not reproduce a transit agency logo.</desc>
      <rect width="64" height="64" rx="14" fill="{INK}"/>
      <path d="M14 47H25C30 47 32 45 32 40V24C32 19 34 17 39 17H50" fill="none" stroke="{IVORY}" stroke-width="5.5" stroke-linecap="round"/>
      <circle cx="14" cy="47" r="5.5" fill="{IVORY}"/>
      <circle cx="32" cy="32" r="5.5" fill="{AMBER}" stroke="{INK}" stroke-width="2.2"/>
      <circle cx="50" cy="17" r="5.5" fill="{IVORY}"/>
    </svg>'''
    (ASSETS / "favicon.svg").write_text(favicon + "\n", encoding="utf-8")
    print(f"Created {target.relative_to(ROOT)}: {target.stat().st_size:,} bytes")
    print(f"Capture {sid}: {len(snapshots)} families, {len(patterns)} patterns, {len(seen)} unique display lines, {display_vertices:,} displayed vertices")
    print("Created assets/favicon.svg: original 64 x 64 route-line symbol")


if __name__ == "__main__":
    main()
