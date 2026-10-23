# How this archive was built

## Scope

This archive covers documented GO **bus** route families, including discontinued numbers, reused numbers, seasonal routes, and bus substitutions that appear in the original data. Train routes themselves are not mapped as bus routes. Each numeric folder groups a number's different eras; it does not imply that two services with the same number have a continuous lineage.

GO bus service began on **8 September 1970**, initially serving the Lakeshore extensions and the Toronto–Newmarket corridor. That network predates the modern route-number system. [Metrolinx's historical account](https://www.metrolinx.com/en/discover/rolling-back-the-clock---the-50-year-evolution-of-the-go-bus) provides the network starting point. Named legacy corridors are documented separately when an operating route number has not been established.

**“All routes” means every route family verified in the sources collected for this archive, not a claim that every version ever operated has been recovered.** The coverage table counts the evidence actually present. Unavailable early timetables, unverified change dates, and missing platform locations are recorded rather than filled with guesses.

## Three kinds of evidence

| Record | What it establishes | What it does not establish |
|---|---|---|
| Original GO GTFS snapshot | Published branch labels, headsigns, directions, complete scheduled stop sequences, boarding restrictions, service dates, and supplied shapes within that feed | The original launch date, actual bus performance, or continuous operation between snapshots |
| Original timetable reconstruction | The particular dated route/branch and timing points shown by the timetable | Every unprinted roadside stop, all local turns, or the exact old bus bay |
| Dated service-change announcement | A launch, change or withdrawal described by the operator or a contemporary report | Unmentioned branch details or a complete stop inventory |

The route history records put a source URL next to each event. A wording such as **“by 2011”** means a snapshot establishes that the service existed by then; it does not claim that it began that year.

## Dates and route numbers

- **Archive filenames can be misleading.** Some files were captured years after their printed effective dates. The original printed date takes priority for manual reconstructions.
- **A timetable table number is not always an operating route number.** Table 52, for example, has held multiple 407 East routes, and much earlier material with that table identifier can refer to an unrelated Yonge service.
- **One number can be reused.** The archive separates different eras of 11, 15, 22, 35, 41, 43, 69 and 94 where supported by evidence.
- **GTFS snapshot dates are capture dates.** A March feed can include an April service change. Each pattern carries its exact `service_dates` plus its first and last scheduled dates.
- **Direction IDs are source values.** `0` and `1` are not universal east/west or north/south labels. Read the headsign and ordered stops.
- **No-trip route definitions do not become mapped service.** The importer requires actual trips with active dates and an ordered stop sequence.

## GTFS extraction

The checked-in manifest identifies four original source ZIPs: 11 January 2016, 8 March 2022, 5 May 2023 and 23 October 2026. Their SHA-256 checksums, feed metadata and counts are in `data/snapshots.json`. The original ZIPs are downloaded reproducibly from the manifest; large raw archives are not duplicated in this repository.

`scripts/import_gtfs.py` retains bus routes (`route_type=3`) and groups trips by **branch, direction, headsign, shape ID, ordered stop IDs and pickup/drop-off restrictions**. It joins each group to all its active service dates. A change in boarding restrictions or supplied geometry is retained as a distinct pattern. Counts therefore describe documented directional patterns, not a count of route numbers or independent permanent route alignments.

Stop IDs and coordinates are preserved from their own dated feed. The same stop name or route number in another year is not automatically treated as the same location or service.

### Supplied shapes and short turns

Source shapes are retained in each snapshot's `shapes` object in a form simplified by approximately 10 metres. Exact unsimplified polylines remain in the original checksummed GTFS ZIPs. Some old feeds reuse a whole-corridor shape for short workings. To avoid drawing a short trip all the way to the main route's terminal, the importer matches the ordered stops to the source polyline and clips the line to the first and last stops.

The matching uses ordered segment projections, including repeated intersections and terminal loops. If a suitable monotonic sequence cannot be found within 800 metres of every stop, the viewer shows **dashed schematic stop connections**, not an invented road alignment. This relatively generous threshold accommodates old generalized source shapes; it does not certify precise bus-lane or driveway geometry. The simplified source line remains available for inspection, and the manifest links to the exact original ZIP.

## Historical map reconstruction

Manual versions retain their original ordered timing-point list. A coordinate may be:

- supplied by an original dated GTFS feed;
- an explicitly sourced station or junction reference point;
- a matched reference stop area from another dated feed, with the reference name and source retained; or
- **unlocated**, with no fabricated latitude/longitude.

Reference matching uses the latest available feed not later than the documented pattern, or the earliest available later feed when no earlier reference exists. Known Union and Scarborough Centre terminal moves are separated by era. Matching a historical station name to a later reference location does not establish its old platform. Relocated terminals are kept distinct where the evidence establishes different sites. If an exact normalized name corresponds to geographically distant records, the script declines to resolve it automatically.

The explicit terminal boundaries used in that matching are [5 December 2020 for Union Station Bus Terminal](https://www.metrolinx.com/en/discover/union-station%27s-new-bus-terminal-opens-doors-for-first-time) and [1 October 2022 for the GO platforms at Scarborough Centre](https://assets.metrolinx.com/image/upload/Documents/Metrolinx/Scarborough-Centre-GO-Bus-FAQ.pdf). The latter move is distinct from the later TTC Line 3 replacement-bus changes.

Most manually reconstructed routes are dashed stop-to-stop diagrams. Route 52 additionally includes twenty documentary corridor reconstructions developed from original timetables, source road geometry, and published reference points. Those lines are explicitly labeled as reconstructions with generalized local approaches. The December 2011 route 52 version includes the Keele / Great Gulf stop verified in the original timetable.

When a historical version has unresolved coordinates, its downloadable SVG is a **stop-order diagram**. Its interactive geographic view plots only established locations and identifies the missing ones in the stop list. `data/unlocated-stops.json` is the open location-research queue.

## Basemap

The geographic background is the Ontario Ministry of Natural Resources' published mainland municipal boundary layer, queried for the GO service region in WGS84. The source server simplified it to 0.001 degrees. The exact query and retrieval date are recorded in `data/basemap-source.json`.

These are modern reference boundaries, not a reconstruction of historical municipal borders. OpenStreetMap-derived road and junction references used for route 52 are credited in the sources document. Map coordinates are longitude, latitude in GeoJSON; CSV columns explicitly name latitude and longitude.

## Timetable catalog

`data/schedule-archive.json` indexes the publicly listed original documents at `archive.gotrain.cc`, including both PDF and older HTML timetables. Route-level `archive-sources.json` files provide related corridor collections and directly cited documents. **Indexing a link does not mean that the document was read or that its table number proves a route.** Related corridor collections can contain predecessor services or different route numbers.

## PDF editions

The [illustrated guide](../pdfs/GO-Bus-History-Guide.pdf) introduces the archive and links to its route documents. Each numbered family has a `routes/NN/route-NN-history.pdf`; each named legacy corridor has a `legacy/<id>/<id>-history.pdf`. Links appear near the top of the route README and interactive viewer, and in the main route index.

The route PDFs combine the sourced chronology, dated maps and numbered stop lists, with bookmarks for navigation. Their dates, stop order and geometry come from the same documented patterns as the web archive. Numbered lists preserve source coverage: older timetable reconstructions may establish only timing points or major stops, while GTFS patterns retain the complete scheduled stop sequence. An unresolved historical location remains explicitly unlocated, and a reference coordinate does not establish an old bus bay. The PDF format does not imply that missing versions or unprinted stops have been recovered.

The PDF builders use the installed DejaVu Sans fonts under `/usr/share/fonts/truetype/dejavu`. Their Python dependencies are listed in `scripts/requirements-pdf.txt`. The checked-in PDFs are ready to read without running the build scripts.

## Reproduction

```sh
python scripts/download_feeds.py --directory .cache/feeds
python scripts/import_gtfs.py --manifest data/feed-manifest.json --feed-dir .cache/feeds
python scripts/build_archive.py
python scripts/validate_archive.py
```

Build the route PDFs and illustrated guide after the archive data has been generated:

```sh
python -m pip install -r scripts/requirements-pdf.txt
python scripts/build_pdfs.py
python scripts/build_pdf_guide.py
```

Run `python -m http.server 8000` and open `http://localhost:8000` to use the interactive viewer. The site itself has no external JavaScript, remote map tiles, analytics, API keys or build-system dependencies. Source links open the cited original websites. Python 3.10 or newer is sufficient for the data scripts; the PDF builders additionally use the packages listed in `scripts/requirements-pdf.txt`.
