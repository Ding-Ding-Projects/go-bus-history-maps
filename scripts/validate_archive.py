#!/usr/bin/env python3
"""Validate cross-file integrity and evidence requirements for the archive."""
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors, count, stop_rows = [], 0, 0
    def check(test, message):
        if not test:
            errors.append(message)
    catalog = json.loads((ROOT / "data/catalog.json").read_text())
    ids = []
    latest = set()
    all_pattern_ids = set()
    for row in catalog["routes"]:
        number = row["route"]
        ids.append(int(number))
        folder = ROOT / "routes" / row["folder"]
        data = json.loads((folder / "data.json").read_text())
        check(data["route"] == number, f"{number}: inconsistent route ID")
        check(bool(data["timeline"]), f"{number}: missing historical timeline")
        for event in data["timeline"]:
            check(bool(event.get("sources")), f"{number}: unsourced event {event.get('date')}")
        patterns = list(data["historic_patterns"])
        for snapshot in data["snapshots"]:
            d = json.loads((folder / "snapshots" / (snapshot["id"] + ".json")).read_text())
            check(d["route"] == number, f"{number}: foreign snapshot route")
            if snapshot["id"] == "2026-10-23":
                latest.add(number)
            for pattern in d["patterns"]:
                check(bool(pattern["service_dates"]), f"{pattern['id']}: no service dates")
                check(pattern["service_dates"] == sorted(set(pattern["service_dates"])), f"{pattern['id']}: service dates not unique/sorted")
                check(pattern["first_service_date"] == pattern["service_dates"][0] and pattern["last_service_date"] == pattern["service_dates"][-1], f"{pattern['id']}: service date range mismatch")
                check(pattern["branch"].startswith(number), f"{pattern['id']}: foreign route branch {pattern['branch']}")
            patterns.extend(d["patterns"])
        expected_rows = 0
        for pattern in patterns:
            pid = pattern["id"]
            check(pid not in all_pattern_ids, f"Duplicate pattern ID: {pid}")
            all_pattern_ids.add(pid)
            check(len(pattern["stops"]) >= 2, f"{pid}: fewer than two stops")
            if "service_dates" not in pattern:
                check(bool(pattern.get("sources")), f"{pid}: no historical source")
            for stop in pattern["stops"]:
                check(bool(stop["name"].strip()), f"{pid}: empty stop name")
                lat, lon = stop.get("lat"), stop.get("lon")
                check((lat is None) == (lon is None), f"{pid}: incomplete coordinate pair")
                if lat is not None:
                    check(42 < lat < 46 and -82 < lon < -76, f"{pid}: coordinate outside southern Ontario: {lon},{lat}")
                    check(bool(stop.get("location_source")), f"{pid}: coordinate without provenance")
            expected_rows += len(pattern["stops"])
        with (folder / "stops.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        check(len(rows) == expected_rows, f"{number}: CSV row count {len(rows)} != {expected_rows}")
        grouped = {}
        for csvrow in rows:
            grouped.setdefault(csvrow["pattern_id"], []).append(csvrow)
        for pattern in patterns:
            actual = grouped.get(pattern["id"], [])
            check([r["stop_name"] for r in actual] == [s["name"] for s in pattern["stops"]], f"{pattern['id']}: CSV order mismatch")
            check([int(r["stop_sequence"]) for r in actual] == list(range(1, len(pattern["stops"])+1)), f"{pattern['id']}: CSV sequence not contiguous")
            check(all(r["direction"] == pattern.get("direction", "") for r in actual), f"{pattern['id']}: manual direction lost in CSV export")
        count += len(patterns)
        stop_rows += len(rows)
        check(row["pattern_count"] == len(patterns), f"{number}: catalog count mismatch")
        geo = json.loads((folder / "maps.geojson").read_text())
        check(geo["type"] == "FeatureCollection", f"{number}: invalid GeoJSON collection")
        for feature in geo["features"]:
            check(feature["properties"]["pattern_id"] in all_pattern_ids, f"{number}: orphan map feature")
            check(len(feature["geometry"]["coordinates"]) >= 2, f"{number}: invalid line")
        for svg in (folder / "maps").glob("*.svg"):
            try:
                ET.parse(svg)
            except ET.ParseError as error:
                errors.append(f"{svg}: invalid SVG: {error}")
        for required in ("README.md", "index.html", "history.json", "archive-sources.json"):
            check((folder / required).exists(), f"{number}: missing {required}")
    check(ids == sorted(set(ids)), "Catalog is not uniquely numerically sorted")
    check(count == catalog["pattern_count"], "Overall pattern count mismatch")
    expected_latest = {x["route"] for x in json.loads((ROOT / "data/snapshots.json").read_text())[-1]["route_counts"]}
    check(latest == expected_latest, "Latest bus-route inventory not completely represented")
    # Two documented anchors catch accidental short-turn and reused-era loss.
    old52 = json.loads((ROOT / "routes/52/snapshots/2016-01-11.json").read_text())
    short52 = [p for p in old52["patterns"] if p["branch"] == "52A"]
    check(bool(short52), "Original 2016 52A short turn missing")
    check(all("Unionville" in p["stops"][0]["name"] or "Unionville" in p["stops"][-1]["name"] for p in short52), "2016 52A incorrectly extended beyond its Unionville endpoint")
    old2011 = next((p for p in json.loads((ROOT / "routes/52/historical-patterns.json").read_text()) if p["id"] == "52-p2011"), None)
    check(old2011 and any("Keele" in s["name"] for s in old2011["stops"]), "2011 route52 Keele timing point missing")
    legacy_patterns, legacy_rows = 0, 0
    for corridor in catalog.get("legacy", []):
        folder = ROOT / "legacy" / corridor["id"]
        data = json.loads((folder / "data.json").read_text())
        patterns = data["historic_patterns"]
        by_id = {p["id"]: p for p in patterns}
        for event in data["timeline"]:
            check(bool(event.get("sources")), f"{corridor['id']}: unsourced legacy event")
        with (folder / "stops.csv").open(newline="") as file:
            rows = list(csv.DictReader(file))
        for pattern in patterns:
            actual = [r for r in rows if r["pattern_id"] == pattern["id"]]
            check([r["stop_name"] for r in actual] == [s["name"] for s in pattern["stops"]], f"{pattern['id']}: legacy CSV order mismatch")
            check(all(r["direction"] == pattern.get("direction", "") for r in actual), f"{pattern['id']}: legacy direction missing")
            check(bool(pattern.get("sources")), f"{pattern['id']}: unsourced legacy pattern")
            for stop in pattern["stops"]:
                check(stop.get("lat") is None or bool(stop.get("location_source")), f"{pattern['id']}: legacy coordinate without source")
        for feature in json.loads((folder / "maps.geojson").read_text())["features"]:
            properties = feature["properties"]
            check(properties["pattern_id"] in by_id, f"{corridor['id']}: orphan legacy map feature")
            check(properties.get("direction") == by_id[properties["pattern_id"]].get("direction", ""), f"{corridor['id']}: legacy GeoJSON direction missing")
        for svg in (folder / "maps").glob("*.svg"):
            try:
                ET.parse(svg)
            except ET.ParseError as error:
                errors.append(f"{svg}: invalid SVG: {error}")
        legacy_patterns += len(patterns)
        legacy_rows += len(rows)
    if errors:
        print("VALIDATION FAILED")
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(ids)} route families; {count} patterns; {stop_rows:,} ordered stop rows; {len(latest)} latest-feed bus families; all source requirements, map files and CSV sequences validated.")
    print(f"PASS: {len(catalog.get('legacy', []))} named legacy corridors; {legacy_patterns} patterns; {legacy_rows} ordered stop rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
