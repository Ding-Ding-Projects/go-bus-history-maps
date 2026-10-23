# Contributing a route-history correction

1. Find an original timetable, operator announcement, contemporary report, or original dated GTFS feed.
2. Establish the date printed inside the original. Keep the archive capture date separately.
3. Verify the operating route and branch, not just the timetable's table number.
4. Add a chronological event to the relevant `data/research/routes-*.json` record, with its source URL.
5. Add an ordered historical pattern only for stops the source actually establishes. State whether they are timing points, major stops, or a full stop list.
6. Give each coordinate a source. Leave an unknown point unlocated; do not guess old terminal platforms. Explicit coordinate aliases live in `data/locations.json`.
7. For route 52's original twenty corridor versions, edit `data/research/route52-corridor-patterns.json`.
8. Run `python scripts/build_archive.py` and `python scripts/validate_archive.py`.
9. Rebuild the route PDFs and illustrated guide with the commands below. PDF links are part of the archive builder's templates; keep the generated README and viewer links consistent with those templates.
10. Open the changed route in the local viewer and its PDF. Inspect the dated maps, numbered stop sequences and PDF bookmarks, and include the source and change in your pull request.

## Rebuild the PDFs

After generating the archive data, install the PDF dependencies and run both builders:

```sh
python -m pip install -r scripts/requirements-pdf.txt
python scripts/build_pdfs.py
python scripts/build_pdf_guide.py
```

The PDFs retain the same evidence limits as the data. Describe older reconstructed sequences as timing points or major stops where that is all the original source establishes. Preserve unknown locations and distinguish schematic connections from supplied or reconstructed corridor geometry. Do not turn a reference stop area into a claim about an exact historical bus bay.

## File contract

| File | Purpose |
|---|---|
| `routes/NN/README.md` | Human-readable history, maps, major-stop sequences, sources and limitations |
| `routes/NN/route-NN-history.pdf` | Sourced history, dated maps and numbered stop lists, with navigation bookmarks |
| `legacy/<id>/<id>-history.pdf` | Equivalent PDF for a named legacy corridor |
| `pdfs/GO-Bus-History-Guide.pdf` | Illustrated archive guide and route PDF index |
| `routes/NN/history.json` | Narrative and event chronology |
| `routes/NN/historical-patterns.json` | Manually established historical versions |
| `routes/NN/snapshots/YYYY-MM-DD.json` | Exact original-feed stop patterns, service dates and source shapes |
| `routes/NN/stops.csv` | Ordered stop rows for every documented pattern |
| `routes/NN/maps.geojson` | Line geometry and evidence metadata for mapped versions |
| `routes/NN/maps/*.svg` | Maps that display directly on GitHub; stop-order diagrams where geography is unresolved |
| `routes/NN/index.html` and `data.json` | Static interactive viewer and its route data |
| `routes/NN/archive-sources.json` | Related archive discovery links; not a reviewed-source claim |

Branch letters are stored under their numeric family. Number reuse remains in one folder with distinct dates, names and source explanations. Named pre-numbered corridors belong under `legacy/` unless evidence establishes an actual operating number.
