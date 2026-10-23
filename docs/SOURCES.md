# Sources and attribution

## Original operating data

- [GO Transit developer resources and data agreement](https://www.gotransit.com/en/partner-with-us/software-developers)
- [Current GO Transit GTFS ZIP](https://assets.metrolinx.com/raw/upload/Documents/Metrolinx/Open%20Data/GO-GTFS.zip)
- [Mobility Database's historical GO feed catalog](https://mobilitydatabase.org/feeds/gtfs/mdb-727), preserving the former OpenMobilityData / TransitFeeds collection
- [Internet Archive's March 2022 copy of the original GO feed](https://web.archive.org/web/20220308054107/https://www.gotransit.com/static_files/gotransit/assets/Files/GO_GTFS.zip)
- [Feed manifest](../data/feed-manifest.json) and [checksums / original feed metadata](../data/snapshots.json)

### Required Metrolinx legend

Data used in this product or service is provided with the permission of Metrolinx. Metrolinx makes no representations or warranties of any kind, express or implied, with respect to the Data and assumes no responsibility for the accuracy or currency of the data used in this product or service.

The project is independent and is not an official GO Transit trip planner. No Metrolinx logos or trademarks are reproduced as branding assets.

## Original timetables and history

- [GO Transit PDF and HTML Schedule Archive](https://archive.gotrain.cc/) — catalog of original GO documents, with archive metadata
- [Transit Toronto's regional schedule collection](https://transittoronto.ca/spare/0061.shtml) — original schedules and contemporary service-change reporting
- [GO / Metrolinx September 2016 ridership report](https://stevemunro.ca/wp-content/uploads/2017/03/ridership-report-september2016.pdf) — original operator report preserved by Steve Munro
- [Metrolinx: 50 years of GO bus service](https://www.metrolinx.com/en/discover/rolling-back-the-clock---the-50-year-evolution-of-the-go-bus)
- [Metrolinx: new Union Station Bus Terminal opens, 5 December 2020](https://www.metrolinx.com/en/discover/union-station%27s-new-bus-terminal-opens-doors-for-first-time)
- [Metrolinx: Scarborough Centre GO platform relocation FAQ, effective 1 October 2022](https://assets.metrolinx.com/image/upload/Documents/Metrolinx/Scarborough-Centre-GO-Bus-FAQ.pdf)

Each route's `history.json`, `historical-patterns.json` and `README.md` identify the actual sources supporting its claims. Secondary historical reports are labeled separately from original timetables and operator announcements. The linked originals retain their respective copyright; this repository does not republish whole third-party articles or timetable PDFs.

## Geography

- [Ontario municipal boundary layer, published ArcGIS service](https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/14) — Ontario Ministry of Natural Resources, **Open Government Licence – Ontario**. [Exact query metadata](../data/basemap-source.json).
- [Ontario municipal boundaries dataset](https://data.ontario.ca/dataset/municipal-boundaries)
- [Open Government Licence – Ontario](https://www.ontario.ca/page/open-government-licence-ontario)
- [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) — **Open Database License (ODbL) 1.0**. Route 52 corridor reconstructions and selected historical junction references contain OpenStreetMap-derived geometry. Modern road geometry is used only as reference geography, not as proof of historical service or historical road configuration.

## Reuse

The underlying Metrolinx, Ontario and OpenStreetMap datasets retain their own terms. A repository-wide software license must not be read as relicensing those datasets. No additional software license has been imposed by this contribution; the repository owner can choose one for the original application code separately.
