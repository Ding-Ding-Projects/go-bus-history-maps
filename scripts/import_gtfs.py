#!/usr/bin/env python3
"""Import dated, original GO GTFS feeds without inferring historical service.

Python standard library only. All bus patterns retain direction, branch,
ordered stops, boarding restrictions, service dates and original shape IDs.
Train routes are excluded. Run from any working directory; see README.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


def read_csv(archive, name):
    if name not in archive.namelist():
        return []
    return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig"))


def iso(value):
    return f"{value[:4]}-{value[4:6]}-{value[6:]}" if len(value) == 8 else value


def simplify(points, tolerance=0.00008):
    """RDP in local degrees (~6–9 metres), preserving every endpoint."""
    if len(points) < 3:
        return points
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        a, b = points[first], points[last]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = dx * dx + dy * dy
        maximum, at = 0, None
        for i in range(first + 1, last):
            p = points[i]
            t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) if length else 0
            dist = (p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2
            if dist > maximum:
                maximum, at = dist, i
        if at is not None and maximum > tolerance * tolerance:
            keep.add(at)
            stack.extend(((first, at), (at, last)))
    return [points[i] for i in sorted(keep)]


def display_geometry(pattern, shapes):
    """Do not let a shared route-wide GTFS shape overstate a short-turn trip.

    Some old feeds reuse one whole-corridor shape across multiple branches.
    Clip only when all stops follow that line in order and lie within 800 m.
    Otherwise show honest schematic stop connections and retain the raw shape
    separately in simplified form for inspection. Exact raw polylines remain
    in the original ZIP. The line is not a reconstruction of road turns.
    """
    stops = [[s["lon"], s["lat"]] for s in pattern["stops"]]
    line = shapes.get(pattern["shape_id"], [])
    if len(line) >= 2:
        scale = math.cos(math.radians(sum(p[1] for p in stops) / len(stops)))
        candidates = []
        # Project to segments rather than vertices. Use dynamic programming to
        # match repeated junctions and terminal loops in the correct stop order.
        for stop in stops:
            row = []
            for i, (a, b) in enumerate(zip(line, line[1:])):
                dx, dy = (b[0] - a[0]) * scale, b[1] - a[1]
                px, py = (stop[0] - a[0]) * scale, stop[1] - a[1]
                squared = dx * dx + dy * dy
                t = max(0, min(1, (px * dx + py * dy) / squared)) if squared else 0
                distance2 = ((px - t * dx) ** 2 + (py - t * dy) ** 2) * 111320 ** 2
                point = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
                if distance2 <= 800 ** 2:
                    row.append((i + t, distance2, point))
            candidates.append(row)
        parents, costs = [], []
        if all(candidates):
            costs = [c[1] for c in candidates[0]]
            parents.append([-1] * len(costs))
            for previous, current in zip(candidates, candidates[1:]):
                at, best, best_cost, next_costs, parent = 0, -1, math.inf, [], []
                for candidate in current:
                    while at < len(previous) and previous[at][0] <= candidate[0] + 1e-8:
                        if costs[at] < best_cost:
                            best_cost, best = costs[at], at
                        at += 1
                    next_costs.append(best_cost + candidate[1])
                    parent.append(best)
                parents.append(parent)
                costs = next_costs
        if costs and math.isfinite(min(costs)):
            index = min(range(len(costs)), key=costs.__getitem__)
            chosen = []
            for row, parent in reversed(list(zip(candidates, parents))):
                chosen.append(row[index])
                index = parent[index]
            chosen.reverse()
            start, end = chosen[0], chosen[-1]
            selected = [start[2]] + line[int(start[0]) + 1:int(math.ceil(end[0]))] + [end[2]]
            selected = [[round(x, 6), round(y, 6)] for x, y in selected]
            clipped = start[0] > 1 or end[0] < len(line) - 2
            pattern["geometry_kind"] = "gtfs-shape-clipped" if clipped else "gtfs-shape"
            pattern["geometry_note"] = "Original feed shape, simplified by approximately 10 metres." + (" Shared corridor shape clipped to this trip's first and last stops; local turns are not independently verified." if clipped else "")
            pattern["geometry"] = {"type": "LineString", "coordinates": selected}
            return
    pattern["geometry_kind"] = "stop-connections"
    pattern["geometry_note"] = "Schematic connections between original GTFS stops. The feed's shape is missing or does not follow this trip's stop order closely enough; no road-level alignment is asserted. A simplified source shape is retained in the snapshot when available."
    pattern["geometry"] = {"type": "LineString", "coordinates": stops}


def ingest(path, spec, output):
    source = dict(spec)
    source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    source["bytes"] = path.stat().st_size
    with ZipFile(path) as z:
        routes = {r["route_id"]: r for r in read_csv(z, "routes.txt") if r["route_type"] == "3"}
        trips = {r["trip_id"]: r for r in read_csv(z, "trips.txt") if r["route_id"] in routes}
        dates = defaultdict(set)
        for row in read_csv(z, "calendar_dates.txt"):
            if row.get("exception_type", "1") == "1":
                dates[row["service_id"]].add(iso(row["date"]))
        # This archive's four feeds use calendar_dates rather than calendar.txt.
        # Refuse an unimplemented format rather than silently dropping service.
        if "calendar.txt" in z.namelist() and list(read_csv(z, "calendar.txt")):
            raise ValueError("Calendar-based feed requires expansion before import")
        feed = list(read_csv(z, "feed_info.txt"))
        source["feed_info"] = feed[0] if feed else {}
        stop_rows = {r["stop_id"]: r for r in read_csv(z, "stops.txt")}
        trip_stops = defaultdict(list)
        for row in read_csv(z, "stop_times.txt"):
            if row["trip_id"] in trips:
                trip_stops[row["trip_id"]].append((int(row["stop_sequence"]), row["stop_id"], row.get("pickup_type", "0") or "0", row.get("drop_off_type", "0") or "0"))
        wanted_shapes = {r.get("shape_id", "") for r in trips.values()}
        shapes = defaultdict(list)
        for row in read_csv(z, "shapes.txt"):
            if row["shape_id"] in wanted_shapes:
                shapes[row["shape_id"]].append((int(row["shape_pt_sequence"]), float(row["shape_pt_lon"]), float(row["shape_pt_lat"])))
        shapes = {sid: simplify([[round(lon, 6), round(lat, 6)] for _, lon, lat in sorted(points)]) for sid, points in shapes.items()}

    grouped = defaultdict(dict)
    for tid, trip in trips.items():
        if not dates.get(trip["service_id"]):
            continue
        number = routes[trip["route_id"]]["route_short_name"]
        ordered = tuple((sid, pickup, dropoff) for _, sid, pickup, dropoff in sorted(trip_stops[tid]))
        if not ordered:
            continue
        key = (trip.get("route_variant") or number, trip.get("direction_id", ""), trip.get("trip_headsign", ""), trip.get("shape_id", ""), ordered)
        if key not in grouped[number]:
            signature = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:12]
            grouped[number][key] = {
                "id": f"{number}-{spec['id']}-{signature}",
                "branch": key[0], "direction_id": key[1], "headsign": key[2],
                "shape_id": key[3], "geometry_kind": "gtfs-shape" if key[3] in shapes else "stop-connections",
                "stops": [{"stop_id": sid, "name": stop_rows[sid]["stop_name"], "lat": float(stop_rows[sid]["stop_lat"]), "lon": float(stop_rows[sid]["stop_lon"]), "pickup_type": pickup, "drop_off_type": dropoff, "accuracy": "original-gtfs", "location_source": spec["url"]} for sid, pickup, dropoff in ordered],
                "service_dates": set(), "trip_count": 0,
            }
        item = grouped[number][key]
        item["service_dates"].update(dates[trip["service_id"]])
        item["trip_count"] += 1

    counts = []
    for number, patterns in sorted(grouped.items(), key=lambda kv: int(kv[0])):
        patterns = list(patterns.values())
        patterns.sort(key=lambda p: (p["branch"], p["headsign"], -len(p["stops"]), p["id"]))
        for item in patterns:
            item["service_dates"] = sorted(item["service_dates"])
            item["first_service_date"] = item["service_dates"][0]
            item["last_service_date"] = item["service_dates"][-1]
            display_geometry(item, shapes)
        names = sorted({r["route_long_name"] for r in routes.values() if r["route_short_name"] == number})
        dataset = {"schema_version": 1, "route": number, "names": names, "snapshot": source, "patterns": patterns, "shapes_note": "Source polylines simplified by approximately 10 metres. Exact unsimplified shapes are in the checksummed original GTFS ZIP.", "shapes": {sid: shapes[sid] for sid in sorted({p["shape_id"] for p in patterns}) if sid in shapes}}
        dest = output / "routes" / number.zfill(2) / "snapshots"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{spec['id']}.json").write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n")
        counts.append({"route": number, "patterns": len(patterns), "stops": len({s['stop_id'] for p in patterns for s in p['stops']})})
    source["route_counts"] = counts
    source["pattern_count"] = sum(c["patterns"] for c in counts)
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--feed-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    result = []
    for spec in manifest:
        source = ingest(args.feed_dir / spec["filename"], spec, args.output)
        result.append(source)
        print(f"{spec['id']}: {len(source['route_counts'])} bus families, {source['pattern_count']} directional patterns", flush=True)
    (args.output / "data").mkdir(exist_ok=True)
    (args.output / "data" / "snapshots.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
