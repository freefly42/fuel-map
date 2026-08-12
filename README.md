# Fuel Map

Fuel Map is an early, standalone fuel-route planning companion for pilots and Stratux. It is a
dependency-free static PWA that loads a checksummed JSON package, accepts routes such as
`KHND-KSJN-KIWS`, plots airports with listed 100LL, and remains usable after a successful
online load.

This repository is the canonical home for the website, data contract, and published data.
The same versioned static website can be hosted publicly or
packaged into Stratux. PiSugar builds may depend on Fuel Map, but Fuel Map has no PiSugar or
Stratux runtime dependency.

## Current state and limits

The checked-in snapshot contains every open, public-use airport in all 50 states from FAA NASR.
Airports advertising 100LL are also written to `config/airports.json` for price updates; airports
without advertised 100LL remain available as route destinations without becoming fuel markers.

The app currently uses a lightweight geographic plot rather than a full aeronautical basemap.
The intended next stages are nationwide label decluttering, public static hosting, and packaging
the same static assets into Stratux.

> **Planning aid only.** Fuel availability and price data can be stale or wrong. Always verify
> fuel, airport status, weather, and current NOTAMs with authoritative sources before flight.

## Run locally

Python is only used as a static file server; the browser app has no package dependencies.
Service workers require HTTPS or the browser's `localhost` secure-context exception.

```sh
cd fuel-map/web
python3 -m http.server 8080
```

Open <http://localhost:8080/>. Loading `web/index.html` directly with a `file:` URL will not work.

The public HTTPS map uses browser Geolocation. A copy hosted on Stratux reads its onboard GPS and
groundspeed from `/getSituation`. Airport details show direct distance in nautical miles and time
at the detected speed; when only position is available, a saved manual groundspeed field appears
beside the size slider. Position and distance calculations stay in the browser.

## Build the data

Import the current FAA NASR `APT_BASE.csv` (or its containing ZIP) first:

```sh
python3 scripts/import_nasr_airports.py /path/to/APT_BASE.csv
```

The importer keeps only open, public-use airports in the 50 states. It writes every such airport
to the data package and writes only airports whose FAA fuel list contains `100LL` to
`config/airports.json`. Existing prices are retained when identifiers match.

The builder consumes the already-saved CSV and metadata snapshot. It performs no network
requests and must not be pointed at a live NOTAM source.

```sh
cd fuel-map
python3 scripts/build_data.py \
  --source-dir /path/to/aviation-fuel-prices
```

The output is deterministic: identical source files produce byte-identical JSON. It writes:

- `data/fuel-airports-v2.json` — deterministic, pretty-printed JSON, compressed automatically during HTTP transfer
- `data/latest.json` — version, coverage, byte count, and SHA-256 manifest

The input directory is intentionally outside this repository. FAA PDFs, report images, caches,
temporary files, and the old generated HTML are not copied into the project.

Fifteen priced-airport rows have no CSV coordinates. `source/coordinate-fallbacks.json`
preserves just the coordinates previously captured by the offline FAA station cache used to
make the saved report; it is not refreshed during a build. Each generated `position.source`
states whether coordinates came from the CSV or that saved fallback.

## Validate

```sh
cd fuel-map
python3 scripts/validate.py
```

The validation checks canonical JSON and its checksum, both v1 schemas, all 50 states, public-use
airport and 100LL queue counts, sample route airports, and the visible-marker count.

The data contract is in [DATA_FORMAT.md](DATA_FORMAT.md), design and integration decisions are
in [ARCHITECTURE.md](ARCHITECTURE.md).

The next development environment can start with
[CLOUDCLI_PROJECT_PROMPT.md](CLOUDCLI_PROJECT_PROMPT.md).
