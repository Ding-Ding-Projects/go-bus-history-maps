# Validation of the 23 October 2026 edition

## Original-feed comparison

The imported patterns were independently compared with the four original checksummed GTFS ZIPs. The comparison covered bus-route inclusion, branch labels, direction IDs, headsigns, shape IDs, ordered stop IDs, pickup/drop-off restrictions, coordinates, trip counts and active service dates. No mismatches were found in that comparison.

| Original capture | Bus families | Extracted patterns | Ordered stop occurrences |
|---|---:|---:|---:|
| 2016-01-11 | 41 | 472 | 8,638 |
| 2022-03-08 | 39 | 324 | 7,225 |
| 2023-05-05 | 37 | 177 | 3,617 |
| 2026-10-23 | 38 | 258 | 4,679 |
| Total | 49 distinct families | 1,231 | 24,159 |

Source URLs, original metadata and SHA-256 checksums are recorded in [the feed manifest](../data/feed-manifest.json) and [snapshot metadata](../data/snapshots.json). The total is a sum of directional service patterns across captures, not a count of permanent routes.

The geometry review found 851 patterns using complete supplied source shapes, 313 using source shapes clipped to their own stop sequence, and 67 using explicitly labeled schematic connections where reliable source geometry was unavailable. Source shapes are simplified for display; the exact original polylines remain in the ZIPs.

## Repository integrity

`python scripts/validate_archive.py` passed for:

- 60 numbered families, 1,428 total documented patterns and 25,329 ordered stop occurrences;
- both named legacy corridors, with 5 additional patterns and 37 stop occurrences;
- complete representation of all 38 bus families operating in the latest captured feed;
- sources on every historical event and manually reconstructed pattern;
- coordinate provenance, valid coordinate pairs and southern Ontario bounds;
- JSON-to-CSV stop order and direction preservation, valid map features and SVG files;
- original 2016 route 52A short-turn endpoints and the December 2011 Keele timing point.

Historical location references were reviewed separately to distinguish former terminals from replacements and reference points from surveyed platforms. Unresolved locations remain in the [research queue](../data/unlocated-stops.json). These checks establish consistency and traceability; they do not certify that every historical operating detail has been recovered.

## Interactive viewer

The local viewer was exercised in Chromium at desktop width and at a 390-pixel phone viewport. The checks covered the 60-route catalog, route search, evidence-date and branch changes, map zoom and fit, ordered stops, retired families, reused numbers, the special UP Express replacement family and both legacy corridors. No JavaScript errors or phone-width horizontal overflow were observed.

SVG map files and page layouts were also visually inspected. The application loads its assets and data locally and makes no map-tile or analytics requests. GitHub's HTML file view is not a running deployment; the README explains how to open the interactive viewer through a local HTTP server.

After the visual redesign, an independent static audit checked all 63 content pages plus the custom 404 page. All 1,326 local links, asset references and fragment targets resolved to existing files or page anchors. The 60 numbered families remain numerically sorted, their catalog counts sum to 1,428 patterns, and both legacy corridors remain separate. All 63 PDFs are linked, including the 62 route and legacy volumes and the illustrated guide. The featured route 52 link selects the existing `52-p2017` pattern in the historical dataset, documented on 2 September 2017. JavaScript syntax validation passed.

A separate HTTP check mounted the site beneath `/go-bus-history-maps/`, matching the GitHub Pages project path. All 537 unique page, asset, route-data, snapshot and download targets returned HTTP 200; HTML, CSS, JSON, SVG and PDF responses had their expected content types. The deployment workflow's staged file scope includes the network graphic, favicon, 404 page, documentation and every PDF, while excluding Git history and research scripts. These local checks establish path compatibility; the release process separately verifies the live deployment.

## Illustrated PDFs

The collection contains 62 route and legacy volumes, totaling 2,472 pages, plus an eight-page illustrated reader's guide. [The PDF manifest](../data/pdf-manifest.json) records each route file's page count, size and exact pattern-to-page index.

An independent comparison checked all 1,433 patterns and 25,366 ordered stop occurrences against the source data. Every source stop name was found within its corresponding pattern's page range. All 1,433 pattern bookmarks and 3,610 internal links target valid pages; 921 external-link annotations have HTTP(S) targets. This URL-format check does not assert that every external website will remain available.

The guide contains links to all 60 numeric route PDFs and both legacy PDFs. All eight guide pages were visually inspected. Route-volume review included covers, dense maps, historical reconstructions, long stop lists, continuation pages, contents and source references. A complete paragraph-boundary audit covered all 2,472 route-volume pages; stop lists reserve a 72-point bottom boundary. Dense map markers are drawn beneath their number callouts, and unknown historical locations remain labelled.

## Limits of the review

Manual reconstructions represent the timing points or major stops established by their cited documents. The 2,128-entry timetable discovery catalog was indexed, not exhaustively transcribed. Each route's chronology and coverage section identifies unresolved dates and missing source material. See [methodology](METHODOLOGY.md) for the distinction between source records, reference geography and reconstruction.
