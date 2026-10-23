#!/usr/bin/env python3
"""Build route folders, source indexes and maps from the checked research inputs.

This script never retrieves a coordinate by guessing. Historical place names
are matched to an explicit reference catalog; unmatched stops remain visible.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGEND = "Data used in this product or service is provided with the permission of Metrolinx. Metrolinx makes no representations or warranties of any kind, express or implied, with respect to the Data and assumes no responsibility for the accuracy or currency of the data used in this product or service."


def dump(path, data, pretty=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")) + "\n")


def norm(name):
    name = name.lower().replace("&", "and")
    name = re.sub(r"\b(station|bus terminal|bus term|terminal|park and ride|park ride|station bus|bus)\b", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def unique_sources(values):
    result = {}
    for value in values:
        if isinstance(value, str):
            value = {"url": value, "title": value}
        if value.get("url"):
            if not value.get("title"):
                value = {**value, "title": value["url"]}
            if value["url"] not in result or result[value["url"]].get("title") == value["url"]:
                result[value["url"]] = value
    return list(result.values())


def station_catalog(snapshots):
    locations = defaultdict(list)
    for dataset in snapshots:
        for pattern in dataset["patterns"]:
            for stop in pattern["stops"]:
                locations[norm(stop["name"])].append((stop, dataset["snapshot"]))
    return locations


def evidence_date(value):
    value = str(value)
    exact = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if exact:
        return exact.group(0)
    for form in ("%d %b %Y", "%d %B %Y", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(value, form).strftime("%Y-%m-%d")
        except ValueError:
            pass
    year = re.search(r"\b(?:19|20)\d{2}\b", value)
    return year.group(0) + "-01-01" if year else "0000-01-01"


def locate(stop, locations, aliases, date=""):
    result = {"name": stop} if isinstance(stop, str) else dict(stop)
    if result.get("lat") is not None and result.get("lon") is not None:
        result.setdefault("accuracy", "reference location; historic platform unverified")
        return result
    alias = aliases.get(result["name"], aliases.get(norm(result["name"])))
    if isinstance(alias, dict):
        result.update(alias)
        return result
    key = norm(alias or result["name"])
    candidates = locations.get(key, [])
    if candidates:
        as_of = evidence_date(date)
        # Known terminal moves must not inherit a platform from the wrong era.
        relocations = {norm("Union Station Bus Terminal"): "2020-12-05", norm("Scarborough Centre Bus Terminal"): "2022-10-01"}
        if key in relocations:
            boundary = relocations[key]
            candidates = [(s, f) for s, f in candidates if (f["id"] >= boundary) == (as_of >= boundary)]
        if not candidates:
            result.update({"lat": None, "lon": None, "accuracy": "unlocated"})
            return result
        # An ambiguous name that occurs kilometres apart is not geocoded.
        lats = [s["lat"] for s, _ in candidates]
        lons = [s["lon"] for s, _ in candidates]
        if max(lats) - min(lats) < .012 and max(lons) - min(lons) < .016:
            prior = [(s, f) for s, f in candidates if f["id"] <= as_of]
            stop_ref, source = max(prior, key=lambda pair: pair[1]["id"]) if prior else min(candidates, key=lambda pair: pair[1]["id"])
            result.update({"lat": stop_ref["lat"], "lon": stop_ref["lon"], "location_source": source["url"], "location_reference_date": source["id"], "location_reference_name": stop_ref["name"], "accuracy": "reference stop area; historical platform unverified"})
            return result
    result.update({"lat": None, "lon": None, "accuracy": "unlocated"})
    return result


def normalize_history(pattern, route, locations, aliases):
    p = dict(pattern)
    p["id"] = str(p.get("id", f"{route}-history-{len(p.get('stops', []))}"))
    p["branch"] = p.get("branch", route)
    p["label"] = p.get("label", p.get("title", p["id"]))
    p["stop_scope"] = "major-stops"
    p["stops"] = [locate(s, locations, aliases, p.get("date", "")) for s in p.get("stops", [])]
    p["sources"] = [s["url"] if isinstance(s, dict) else s for s in p.get("sources", [])]
    if not p.get("geometry"):
        p["geometry_kind"] = "stop-connections"
        p["geometry"] = {"type": "LineString", "coordinates": [[s["lon"], s["lat"]] for s in p["stops"] if s.get("lat") is not None and s.get("lon") is not None]}
        p["geometry_note"] = "Schematic straight connections between established stop areas, not a street-by-street reconstruction. " + p.get("notes", "")
    else:
        p.setdefault("geometry_note", p.get("notes", "Reconstructed historical corridor; local approaches generalized."))
    missing = [s["name"] for s in p["stops"] if s.get("lat") is None or s.get("lon") is None]
    if missing:
        p["geometry_note"] += f" {len(missing)} stop locations remain unestablished; the full ordered sequence is preserved in the list."
    p["geometry_note"] = p["geometry_note"].strip()
    return p


def mercator(p):
    return p[0] * math.pi / 180, math.log(math.tan(math.pi / 4 + p[1] * math.pi / 360))


def svg_map(title, subtitle, patterns, land):
    esc = html.escape
    coords = [p for pattern in patterns for p in pattern.get("geometry", {}).get("coordinates", [])]
    stops = [s for p in patterns for s in p["stops"] if s.get("lat") is not None and s.get("lon") is not None]
    coords.extend([s["lon"], s["lat"]] for s in stops)
    if not coords:
        return schematic_svg(title, subtitle, patterns[0])
    points = list(map(mercator, coords))
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(880 / max(xmax - xmin, .0012), 400 / max(ymax - ymin, .0008))
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    def xy(p):
        x, y = mercator(p)
        return 500 + (x - cx) * scale, 315 - (y - cy) * scale
    def path(points):
        return " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(map(xy, points)))
    body = []
    minlon, maxlon = min(p[0] for p in coords) - .2, max(p[0] for p in coords) + .2
    minlat, maxlat = min(p[1] for p in coords) - .15, max(p[1] for p in coords) + .15
    for f in land["features"]:
        g = f["geometry"]
        rings = g["coordinates"] if g["type"] == "Polygon" else [r for poly in g["coordinates"] for r in poly]
        flat = [p for r in rings for p in r]
        if max(p[0] for p in flat) < minlon or min(p[0] for p in flat) > maxlon or max(p[1] for p in flat) < minlat or min(p[1] for p in flat) > maxlat:
            continue
        body.append(f'<path d="{" ".join(path(r)+"Z" for r in rings)}" fill="#f1f0e6" stroke="#d3d9cf" stroke-width=".6" fill-rule="evenodd"/>')
    for pattern in patterns:
        c = pattern.get("geometry", {}).get("coordinates", [])
        if len(c) < 2:
            continue
        dashed = ' stroke-dasharray="6 5"' if "connections" in pattern.get("geometry_kind", "") else ""
        body.append(f'<path d="{path(c)}" fill="none" stroke="#216b50" stroke-width="{2 if len(patterns)>1 else 3}" stroke-opacity="{.45 if len(patterns)>1 else 1}" stroke-linejoin="round"{dashed}/>')
    unique = {(round(s["lon"], 4), round(s["lat"], 4)): s for s in stops}
    for i, ((lon, lat), stop) in enumerate(unique.items()):
        x, y = xy([lon, lat])
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{2.1 if len(unique)>40 else 3.5}" fill="#fffef9" stroke="#216b50" stroke-width="1.3"><title>{esc(stop["name"])}</title></circle>')
        if len(patterns) == 1 and len(unique) < 35:
            body.append(f'<text x="{x+6:.1f}" y="{y-7:.1f}" fill="#183a32" font-size="11" font-weight="700" stroke="#fffef9" stroke-width="3" paint-order="stroke">{i+1}</text>')
    subtitle = subtitle[:125]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="620" viewBox="0 0 1000 620" role="img" aria-label="{esc(title)}">
<rect width="1000" height="620" fill="#fffef9"/><defs><clipPath id="frame"><rect x="20" y="98" width="960" height="440" rx="9"/></clipPath></defs>
<g font-family="system-ui,sans-serif"><text x="28" y="35" font-size="12" fill="#53645f" letter-spacing="2">GO BUS HISTORY MAPS</text><text x="28" y="65" font-size="24" font-weight="700" fill="#183a32">{esc(title[:80])}</text><text x="28" y="86" font-size="12" fill="#53645f">{esc(subtitle)}</text>
<g clip-path="url(#frame)"><rect x="20" y="98" width="960" height="440" fill="#dcecf0"/>{''.join(body)}</g>
<text x="28" y="560" font-size="12" fill="#183a32">{len(patterns)} pattern(s) · {len(unique)} mapped stop locations · dashed lines are schematic connections</text>
<text x="28" y="582" font-size="11" fill="#53645f">Choose individual branches, directions and ordered stop lists in index.html. Sources accompany each version.</text><text x="28" y="603" font-size="10" fill="#53645f">Data: GO Transit / Metrolinx. Basemap: Ontario Ministry of Natural Resources. Independent historical archive.</text></g></svg>\n'''


def schematic_svg(title, subtitle, pattern):
    esc = html.escape
    height = max(300, 150 + len(pattern["stops"]) * 42)
    body = [f'<line x1="44" x2="44" y1="120" y2="{108 + len(pattern["stops"]) * 42}" stroke="#216b50" stroke-width="3"/>']
    for i, s in enumerate(pattern["stops"]):
        y = 126 + i * 42
        body.append(f'<circle cx="44" cy="{y}" r="12" fill="#fffef9" stroke="#216b50"/><text x="44" y="{y+4}" text-anchor="middle" font-size="11">{i+1}</text><text x="68" y="{y+5}" font-size="15">{esc(s["name"])}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" role="img" aria-label="{esc(title)}"><rect width="100%" height="100%" fill="#fffef9"/><g font-family="system-ui,sans-serif" fill="#183a32"><text x="24" y="37" font-size="24" font-weight="700">{esc(title)}</text><text x="24" y="65" font-size="13">{esc(subtitle[:100])}</text><text x="24" y="87" font-size="12">Stop-order diagram. Geography has not been established for every historical stop.</text>{"".join(body)}</g></svg>\n'


def route_html(route):
    pdf_filename = f"route-{str(route).zfill(2)}-history.pdf" if str(route).isdigit() else f"{route}-history.pdf"
    return f'''<!doctype html>
<html lang="en" data-root="../../" data-route="{route}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>GO {route} · Route history</title><link rel="stylesheet" href="../../assets/style.css"><script defer src="../../assets/map.js"></script></head><body><div class="shell">
<header class="topbar"><a class="brand" href="../../index.html">GO bus <span>history maps</span></a><a href="README.md">Read route folder ↗</a></header>
<main><section class="route-hero"><div class="eyebrow"><a href="../../index.html">All routes</a> / Route {route} / <span id="route-status"></span></div><div class="route-heading"><span class="number" id="route-number">{route}</span><div><h1 id="route-title">Loading route history…</h1><p class="lede" id="route-description"></p><nav class="route-links"><a href="{pdf_filename}" download><strong>Download history PDF ↓</strong></a><a href="#history">History</a><a href="#source-heading">Sources</a><a href="stops.csv" download>Stop lists CSV ↓</a><a href="maps.geojson" download>Map data GeoJSON ↓</a><a href="archive-sources.json">Timetable archive</a></nav></div></div></section>
<div id="app-status" class="loading" role="status">Loading original route data…</div>
<section class="map-workspace" aria-label="Historical route map"><div class="map-controls"><div class="field"><label for="version">1 · Choose the evidence date</label><select id="version"></select></div><div class="field"><label for="pattern">2 · Choose a branch and direction</label><select id="pattern"></select></div></div>
<div class="map-grid"><div class="map-panel"><div class="map-heading"><b id="pattern-heading"></b><span id="pattern-dates"></span></div><svg id="map" class="map-canvas" viewBox="0 0 1000 570" tabindex="0" aria-label="Geographic route map. Drag to pan. Use plus, minus, or zero to zoom or reset."></svg><div class="map-tools"><button id="zoom-in" title="Zoom in" aria-label="Zoom in">+</button><button id="zoom-out" title="Zoom out" aria-label="Zoom out">−</button><button id="fit-map" title="Fit route" aria-label="Fit route">⌂</button></div><div class="map-caption"><div id="map-note"></div><div class="source-links" id="pattern-source"></div><p id="map-description">Numbers connect the markers to the ordered list. Click a marker to find its stop. Solid lines follow supplied or reconstructed corridors; dashed lines connect stop areas schematically.</p></div></div><aside class="stops-panel" aria-label="Ordered stops"><div class="stops-title"><strong id="stop-count">Stop sequence</strong></div><ol class="stop-list" id="stops"></ol></aside></div></section>
<details id="service-detail" hidden><summary>Exact service dates in the selected GTFS pattern</summary><p id="service-dates"></p></details>
<div class="route-bottom"><section id="history"><h2>Route history</h2><ol id="timeline" class="timeline"></ol></section><aside><section class="gaps"><h3>What the evidence covers</h3><ul id="gaps"></ul><a href="../../docs/METHODOLOGY.md">How the maps were made</a></section><h2 id="source-heading" style="margin-top:28px">Sources</h2><ol id="sources" class="source-list"></ol></aside></div></main>
<footer class="footer"><nav><a href="../../index.html">All route histories</a><a href="../../docs/COVERAGE.md">Coverage</a><a href="../../docs/SOURCES.md">Attribution</a></nav><p>{LEGEND}</p><p>Ontario municipality geometry: Ontario Ministry of Natural Resources, Open Government Licence – Ontario. Historical stop areas do not establish the location of an old bus platform. This is an independent history archive, not a live trip planner.</p></footer></div></body></html>\n'''


def build_legacy(research_dir, locations, aliases, land, unlocated):
    source = research_dir / "legacy-corridors.json"
    if not source.exists():
        return []
    entries = []
    intro = ["# Named legacy GO bus corridors", "", "These services predate or sit outside the verified modern route-number catalog. A timetable identifier such as Table 58 or Table 52 is preserved as source metadata, not assigned as a modern operating route number.", ""]
    for record in json.loads(source.read_text()):
        identifier = record["id"]
        patterns = [normalize_history(p, identifier, locations, aliases) for p in record["historic_patterns"]]
        folder = ROOT / "legacy" / identifier
        (folder / "maps").mkdir(parents=True, exist_ok=True)
        data = {"schema_version": 1, "route": identifier, "name": record["name"], "status": "discontinued", "description": record["description"], "timeline": record["timeline"], "historic_patterns": patterns, "sources": unique_sources(record["sources"]), "gaps": record["gaps"], "snapshots": []}
        dump(folder / "data.json", data)
        dump(folder / "history.json", record, True)
        dump(folder / "archive-sources.json", {"documents": record["sources"]}, True)
        (folder / "index.html").write_text(route_html(identifier))
        features, rows = [], []
        readme = [f"# {record['name']}", "", record["description"], "", f"[Download history PDF]({identifier}-history.pdf) · [Interactive map](index.html) · [Ordered stops CSV](stops.csv) · [GeoJSON](maps.geojson)", "", "The PDF includes the sourced history, dated maps, numbered stop lists and navigation bookmarks. Older versions retain the timetable timing-point or major-stop limits described below.", "", "## History", ""]
        for event in record["timeline"]:
            readme += [f"### {event['date']}", "", event["event"], "", " · ".join(f"[Source {i+1}]({u})" for i,u in enumerate(event["sources"])), ""]
        readme += ["## Documented maps and stop sequences", ""]
        for p in patterns:
            filename = p["id"] + ".svg"
            incomplete = any(s.get("lat") is None for s in p["stops"])
            (folder / "maps" / filename).write_text(schematic_svg(record["name"], p["label"], p) if incomplete else svg_map(record["name"], p["label"], [p], land))
            readme += [f"### {p['date']} — {p['label']}", "", f"![{p['label']}](maps/{filename})", "", " → ".join(s["name"] for s in p["stops"]), "", p["geometry_note"], "", " · ".join(f"[Original source {i+1}]({u})" for i,u in enumerate(p["sources"])), ""]
            if len(p["geometry"].get("coordinates", [])) >= 2:
                features.append({"type": "Feature", "properties": {"corridor": identifier, "pattern_id": p["id"], "date": p["date"], "direction": p.get("direction", ""), "geometry_kind": p["geometry_kind"], "sources": p["sources"]}, "geometry": p["geometry"]})
            for i,s in enumerate(p["stops"],1):
                rows.append([identifier,p["id"],p["date"],p.get("direction",""),i,s["name"],s.get("lat"),s.get("lon"),s.get("accuracy")," | ".join(p["sources"]),s.get("location_source","")])
                if s.get("lat") is None or s.get("lon") is None:
                    unlocated.append({"corridor":identifier,"pattern":p["id"],"stop":s["name"],"source":p["sources"][0] if p["sources"] else ""})
        dump(folder / "maps.geojson", {"type":"FeatureCollection","features":features})
        with (folder / "stops.csv").open("w",newline="") as file:
            writer=csv.writer(file, lineterminator="\n")
            writer.writerow(["corridor","pattern_id","date","direction","stop_sequence","stop_name","latitude","longitude","location_accuracy","pattern_sources","location_source"])
            writer.writerows(rows)
        readme += ["## Coverage and unresolved questions", ""] + ["- "+g for g in record["gaps"]] + ["", "## Sources", ""]
        readme += [f"- [{s['title']}]({s['url']})" for s in record["sources"]]
        readme += ["",LEGEND,""]
        (folder / "README.md").write_text("\n".join(readme))
        intro.append(f"- [{record['name']}]({identifier}/README.md) — {len(patterns)} documented versions · [PDF]({identifier}/{identifier}-history.pdf).")
        entries.append({"id":identifier,"name":record["name"],"patterns":len(patterns),"history_events":len(record["timeline"]),"unlocated_stops":sum(1 for s in unlocated if s.get("corridor")==identifier),"url":f"legacy/{identifier}/index.html"})
    (ROOT / "legacy" / "README.md").write_text("\n".join(intro)+"\n")
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-dir", type=Path, default=ROOT / "data" / "research")
    args = parser.parse_args()
    researched = {}
    for file in sorted(args.research_dir.glob("routes-*.json")):
        content = json.loads(file.read_text())
        if isinstance(content, dict):
            content = content.get("routes", [])
        for record in content:
            researched[str(record["route"])] = record
    route52 = args.research_dir / "route52-corridor-patterns.json"
    if route52.exists():
        researched.setdefault("52", {"route": "52"}).setdefault("historic_patterns", []).extend(json.loads(route52.read_text()))
    all_datasets = [json.loads(p.read_text()) for p in sorted((ROOT / "routes").glob("*/snapshots/*.json"))]
    by_route = defaultdict(list)
    for d in all_datasets:
        by_route[d["route"]].append(d)
    locations = station_catalog(all_datasets)
    alias_file = ROOT / "data" / "locations.json"
    aliases = json.loads(alias_file.read_text()) if alias_file.exists() else {}
    land = json.loads((ROOT / "assets" / "ontario-mainland.geojson").read_text())
    archive = json.loads((ROOT / "data" / "schedule-archive.json").read_text())
    family_file = ROOT / "data" / "archive-families.json"
    family_lookup = json.loads(family_file.read_text()) if family_file.exists() else {}
    routes = sorted(set(researched) | set(by_route), key=int)
    catalog, unlocated = [], []
    for route in routes:
        datasets = sorted(by_route[route], key=lambda d: d["snapshot"]["id"])
        research = researched.get(route, {})
        latest = datasets[-1] if datasets else None
        current = any(d["snapshot"]["id"] == "2026-10-23" for d in datasets)
        history = [normalize_history(p, route, locations, aliases) for p in research.get("historic_patterns", [])]
        status = research.get("status", "current" if current else "discontinued")
        if current and status not in ("special",):
            status = "current"
        name = research.get("name", latest["names"][0] if latest else "Historical GO bus route")
        source_values = list(research.get("sources", []))
        for d in datasets:
            source_values.append({"url": d["snapshot"]["url"], "title": f"GO Transit original GTFS snapshot {d['snapshot']['id']}", "type": "original-gtfs"})
        for p in history:
            source_values.extend(p["sources"])
        timeline = research.get("timeline", [])
        gaps = list(research.get("gaps", []))
        if route not in researched:
            gaps.append("An original GTFS record verifies this family, but its earlier narrative history requires further primary-source research.")
        if datasets:
            gaps.append("GTFS dates identify captured feeds, not necessarily the first or last day of a route. Open a pattern to see its exact scheduled service dates. Temporary rail replacement and special-service patterns are included when present in the source.")
        if history:
            gaps.append("Manually reconstructed versions generally contain published timetable timing points / major stops. They must not be read as complete roadside stop inventories.")
        data = {"schema_version": 1, "route": route, "name": name, "status": status, "description": research.get("description", "Original dated GO bus service records, with their branch labels, directions and stop sequences preserved."), "timeline": timeline, "historic_patterns": history, "sources": unique_sources(source_values), "gaps": list(dict.fromkeys(gaps)), "snapshots": [{"id": d["snapshot"]["id"], "pattern_count": len(d["patterns"]), "names": d["names"], "feed_info": d["snapshot"].get("feed_info", {})} for d in datasets]}
        folder = ROOT / "routes" / route.zfill(2)
        folder.mkdir(parents=True, exist_ok=True)
        dump(folder / "data.json", data)
        dump(folder / "history.json", {k: data[k] for k in ("route", "name", "status", "description", "timeline", "sources", "gaps")}, True)
        dump(folder / "historical-patterns.json", history, True)
        (folder / "index.html").write_text(route_html(route))
        family_names = set(family_lookup.get(route, []))
        linked = {s["url"] for s in data["sources"]}
        documents = [a for a in archive if a["family"] in family_names or a["url"] in linked]
        dump(folder / "archive-sources.json", {"note": "Catalog links, not a claim that every document was reviewed. Archive filenames/table numbers are not reliable public route identifiers; verify the original content.", "documents": documents})
        features, rows, map_links = [], [], []
        maps_dir = folder / "maps"
        maps_dir.mkdir(exist_ok=True)
        groups = [(d["snapshot"]["id"], d["patterns"], [d["snapshot"]["url"]]) for d in datasets]
        groups += [("history-" + p["id"], [p], p["sources"]) for p in history]
        for snapshot_id, patterns, sources in groups:
            label = patterns[0].get("date", snapshot_id) if snapshot_id.startswith("history-") else snapshot_id + " GTFS snapshot"
            title = f"Route {route} · {patterns[0].get('branch', route)}" if snapshot_id.startswith("history-") else f"Route {route} · {name}"
            filename = re.sub(r"[^a-zA-Z0-9_.-]", "-", snapshot_id) + ".svg"
            if len(patterns) == 1 and any(s.get("lat") is None for s in patterns[0]["stops"]):
                visual = schematic_svg(title, label, patterns[0])
            else:
                visual = svg_map(title, label, patterns, land)
            (maps_dir / filename).write_text(visual)
            map_links.append((label, filename, len(patterns)))
            for p in patterns:
                feature_sources = p.get("sources", sources)
                props = {"route": route, "pattern_id": p["id"], "branch": p.get("branch", route), "date": p.get("date", snapshot_id), "headsign": p.get("headsign", p.get("label", "")), "direction_id": p.get("direction_id", ""), "direction": p.get("direction", ""), "geometry_kind": p.get("geometry_kind", "stop-connections"), "sources": feature_sources, "first_service_date": p.get("first_service_date"), "last_service_date": p.get("last_service_date")}
                geometry = p.get("geometry")
                if geometry and len(geometry.get("coordinates", [])) >= 2:
                    features.append({"type": "Feature", "properties": props, "geometry": geometry})
                for i, s in enumerate(p["stops"], 1):
                    rows.append([route, snapshot_id, p["id"], p.get("branch", route), p.get("direction_id", ""), p.get("direction", ""), p.get("headsign", p.get("label", "")), i, s.get("stop_id", ""), s["name"], s.get("lat"), s.get("lon"), s.get("pickup_type", ""), s.get("drop_off_type", ""), s.get("accuracy", ""), p.get("first_service_date", ""), p.get("last_service_date", ""), " | ".join(feature_sources), s.get("location_source", "")])
                    if s.get("lat") is None or s.get("lon") is None:
                        unlocated.append({"route": route, "pattern": p["id"], "stop": s["name"], "source": feature_sources[0] if feature_sources else ""})
        expected_maps = {item[1] for item in map_links}
        for stale in maps_dir.glob("*.svg"):
            if stale.name not in expected_maps:
                stale.unlink()
        dump(folder / "maps.geojson", {"type": "FeatureCollection", "name": f"GO route {route} documented patterns", "features": features})
        with (folder / "stops.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(["route", "snapshot", "pattern_id", "branch", "direction_id", "direction", "headsign", "stop_sequence", "stop_id", "stop_name", "latitude", "longitude", "pickup_type", "drop_off_type", "location_accuracy", "first_service_date", "last_service_date", "pattern_sources", "location_source"])
            writer.writerows(rows)
        pattern_count = sum(len(d["patterns"]) for d in datasets) + len(history)
        catalog.append({"route": route, "folder": route.zfill(2), "name": name, "status": status, "aliases": sorted({n for d in datasets for n in d["names"]}), "pattern_count": pattern_count, "history_events": len(timeline), "snapshot_dates": [d["snapshot"]["id"] for d in datasets], "historical_patterns": len(history), "unlocated_stops": sum(1 for x in unlocated if x["route"] == route)})
        readme = [f"# GO route {route} — {name}", "", data["description"], "", f"**Status:** {status}. **Documented patterns:** {pattern_count}. **Research date:** 23 October 2026.", "", f"[Download history PDF](route-{route.zfill(2)}-history.pdf) · [Interactive map](index.html) · [All ordered stops (CSV)](stops.csv) · [All mapped versions (GeoJSON)](maps.geojson) · [History data](history.json) · [Timetable archive links](archive-sources.json)", "", "The PDF includes the sourced history, dated maps, numbered stop lists and navigation bookmarks. Older versions retain the timetable timing-point or major-stop limits described below.", "", "Open `index.html` through the repository's local web server to use the map. SVG maps below display directly on GitHub.", ""]
        if map_links:
            preferred = next((x for x in map_links if x[1] == "2026-10-23.svg"), map_links[-1])
            readme += [f"![Route {route}: {preferred[0]}](maps/{preferred[1]})", ""]
        readme += ["## History", ""]
        for event in timeline:
            refs = " · ".join(f"[Source {i+1}]({u})" for i, u in enumerate(event.get("sources", [])))
            readme += [f"### {event['date']}", "", event["event"], "", refs, ""]
        readme += ["## Maps by documented version", "", "Feed maps combine the patterns present in that dated file. The interactive viewer separates every branch and direction. A feed snapshot can include future or temporary service; its filename is not a route-change date.", "", "| Date / evidence | Map | Patterns |", "|---|---|---:|"]
        for label, filename, count in map_links:
            readme.append(f"| {label} | [SVG map](maps/{filename}) | {count} |")
        readme += ["", "## Historical major-stop sequences", "", "These are timetable timing points / major stops, not necessarily every roadside stop. Full GTFS sequences are in `stops.csv` and the snapshot files.", ""]
        for p in history:
            readme += [f"### {p.get('date','Date in source')} — {p['branch']}: {p['label']}", "", " → ".join(s["name"] for s in p["stops"]), "", p["geometry_note"], "", " · ".join(f"[Original source {i+1}]({u})" for i, u in enumerate(p["sources"])), ""]
        readme += ["## Coverage and unresolved questions", ""] + ["- " + g for g in data["gaps"]] + ["", "## Sources", ""]
        readme += [f"- [{s['title']}]({s['url']}) — {s.get('type','source')}" for s in data["sources"]]
        readme += ["", "## Data attribution", "", LEGEND, "", "Basemap: Ontario Ministry of Natural Resources, Open Government Licence – Ontario. See [methodology](../../docs/METHODOLOGY.md) for geometry and date limitations.", ""]
        (folder / "README.md").write_text("\n".join(readme))
    legacy = build_legacy(args.research_dir, locations, aliases, land, unlocated)
    dump(ROOT / "data" / "catalog.json", {"as_of": "2026-10-23", "routes": catalog, "legacy": legacy, "pattern_count": sum(c["pattern_count"] for c in catalog), "archive_document_count": len(archive)}, True)
    (ROOT / "docs").mkdir(exist_ok=True)
    dump(ROOT / "data" / "unlocated-stops.json", unlocated, True)
    coverage = ["# Coverage by route", "", "This is a documentary archive of the route families verified in the collected sources. It does not claim that every intermediate timetable, temporary diversion or roadside stop since 1970 survives in the available record. An archive link is discovery metadata; only linked evidence in a history or pattern has been used to establish that claim.", "", "| Route | Family | History entries | Manual versions | GTFS patterns | Unlocated historical stop occurrences |", "|---|---|---:|---:|---:|---:|"]
    for r in catalog:
        coverage.append(f"| [{r['route']}](../routes/{r['folder']}/README.md) | {r['name']} | {r['history_events']} | {r['historical_patterns']} | {r['pattern_count']-r['historical_patterns']} | {r['unlocated_stops']} |")
    coverage += ["", "## Named legacy corridors", "", "| Corridor | History entries | Manual versions | Unlocated historical stop occurrences |", "|---|---:|---:|---:|"]
    for item in legacy:
        coverage.append(f"| [{item['name']}](../legacy/{item['id']}/README.md) | {item['history_events']} | {item['patterns']} | {item['unlocated_stops']} |")
    coverage += ["", "## Unlocated stops", "", "An unlocated stop is retained in its ordered sequence. A stop-order diagram is supplied when geography is incomplete; it is not silently placed at a guessed coordinate. [Machine-readable queue](../data/unlocated-stops.json).", ""]
    (ROOT / "docs" / "COVERAGE.md").write_text("\n".join(coverage))
    print(f"Built {len(catalog)} families, {sum(c['pattern_count'] for c in catalog)} patterns, {len(unlocated)} unlocated historical stop occurrences.")


if __name__ == "__main__":
    main()
