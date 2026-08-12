# Fuel Data Format v2

Two UTF-8 JSON documents form the public contract. Property order is not significant even
though the builder sorts keys for deterministic output. Timestamps are ISO 8601 UTC strings.
Nullable fields use JSON `null`, not an empty string.

## `data/latest.json`

This small manifest is fetched before the larger package.

| Field | Meaning |
|---|---|
| `schema` | Literal `fuel-airports-latest/v1`. |
| `schema_version` | Integer `1`. |
| `data_version` | Immutable identifier derived from the source retrieval timestamp. |
| `generated_at` | Timestamp embedded in the saved source metadata. |
| `notam_snapshot_at` | Timestamp of the preserved NOTAM search; not a live-status claim. |
| `artifact.path` | Relative path `fuel-airports-v2.json`. |
| `artifact.media_type` | Media type `application/json`. |
| `artifact.bytes` | JSON byte count before optional HTTP content encoding. |
| `artifact.sha256` | Lowercase SHA-256 of the canonical JSON bytes. |
| `coverage` | Same coverage summary carried by the data package. |

Clients should request the artifact as `<path>?v=<data_version>`, verify `bytes` and `sha256`,
parse it, and then validate its schema and matching `data_version`.

## `data/fuel-airports-v2.json`

The file contains one canonical JSON object followed by a newline. HTTP servers may gzip it
during transfer; browsers transparently decode that content encoding before validation.

| Top-level field | Meaning |
|---|---|
| `schema` | Literal `fuel-airports/v2`. |
| `schema_version` | Integer `2`. |
| `data_version` | Must equal the manifest value. |
| `generated_at` | Source retrieval/generation timestamp. |
| `notam_snapshot_at` | Timestamp of the saved NOTAM lookup. |
| `coverage.scope` | Explicit scope label for public airports and restricted fuel airports in all 50 states. |
| `coverage.states` | Exact included state names and postal codes. |
| `coverage.airport_count` | Number of airport objects. |
| `coverage.public_airport_count` | Number of public-use airport objects. |
| `coverage.restricted_airport_count` | Number of private-use 100LL airports shown for emergency awareness. |
| `coverage.fuel_airport_count` | Airports whose FAA fuel list advertises 100LL. |
| `coverage.visible_fuel_marker_count` | 100LL airports not suppressed by `fuel_unavailable`. |
| `state_average_100ll_price_usd_per_gallon` | Current lower-48 average-price lookup keyed by state code. |
| `sources` | Human-readable provenance and Chart Supplement effective period. |
| `airports` | Airport objects sorted by identifier. |

Each airport object contains:

| Field | Type and meaning |
|---|---|
| `id` | Source airport identifier; do not assume every local identifier has four characters. |
| `faa_id` | FAA location identifier used by NOTAMs and NASR. |
| `name`, `city`, `state`, `state_code` | Display/location strings. |
| `facility_use` | `public`, or `restricted` for private-use airports that advertise 100LL. |
| `position.latitude`, `position.longitude` | Decimal-degree numbers, WGS 84; west is negative. |
| `position.source` | Coordinate provenance label. |
| `services.fuel_100ll` | Boolean source assertion that 100LL is listed. |
| `services.self_service_100ll` | Boolean or `null` when the mode is not specified. |
| `services.full_service_100ll` | Boolean or `null` when the mode is not specified. |
| `deal_rating` | `0` for ordinary airports, `1` for a Great Deal, or `2` for a highlighted Super Deal. |
| `fuel_24_hours` | Boolean, or `null` when 24-hour fuel availability is unknown. |
| `fuel_24_hours_source` | Optional source label or URL for the 24-hour determination. |
| `fuel_checked_at` | Optional timestamp of the latest successful price lookup for this airport, including lookups that returned no price. |
| `fuel_unavailable` | Boolean UI suppression flag derived from the saved fuel NOTAM details. |
| `notams` | Preserved matching NOTAM detail objects; empty when none were saved. |
| `notam_checked_at` | Optional timestamp of the latest official FAA refresh for this airport. |
| `offers` | One or more source/provider records. |
| `availability_source_url` | Source used for the airport's 100LL listing, or `null`. |

An offer contains `provider`, optional generic `price_usd_per_gallon` when the source does not identify
the service mode, nullable numeric `full_service_price_usd_per_gallon` and
`self_service_price_usd_per_gallon`, nullable ISO date `price_date`, nullable integer
`price_age_days` measured at `generated_at`, nullable `source_updated`, and nullable
`source_url`. A missing price is unknown, not zero.

A parsed NOTAM contains `number`, `starts_at`, `ends_at`, `text`, and `active`. Older snapshots may
also contain `raw`. Consumers must keep NOTAM-affected airports in route lookup and detail views,
but must not render `fuel_unavailable: true` airports as ordinary fuel markers.

## Compatibility

Readers must reject unsupported `schema` values. New optional fields may be added within v1;
readers should ignore unknown fields. Renaming/removing fields, changing units or meanings, or
changing required types requires v2 filenames and schema identifiers.
