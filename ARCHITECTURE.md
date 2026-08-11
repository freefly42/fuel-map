# Fuel Route Architecture

## Product boundary

The current deliverable is a static proof of concept with a four-state snapshot. The target is
an offline-first CONUS 48-state PWA that can be hosted independently and later served or
embedded by Stratux without changing its data model. It is a planning aid, not an authoritative
dispatch or preflight source.

## Static application and offline behavior

`web/index.html`, `web/app.css`, and `web/app.js` use browser-native APIs. There is no JavaScript build step
or runtime server. `web/sw.js` caches the application shell. The app obtains `latest.json`
network-first and stores the JSON artifact under a URL qualified by `data_version`. After one
complete load, the last known-good shell, manifest, and data remain available offline.

The browser verifies byte count, SHA-256, schema, and matching data
version before committing the artifact and then its manifest to a verified Cache Storage entry.
A failed network load falls back to the prior verified pair rather than silently accepting data or
stranding an older artifact behind a newer manifest.

## Route parsing and rendering

Route input is normalized to uppercase and split on hyphens, commas, or whitespace. Each token
is looked up by the exact airport identifier in the loaded package. Known waypoints are joined
in entered order; missing identifiers are called out rather than guessed.

The current map is a native SVG geographic projection over the snapshot's bounds. It avoids an
online tile dependency and proves route/marker behavior offline. Route labels are always shown;
other airport labels appear beyond a zoom threshold. A nationwide implementation should keep
that zoom-dependent policy, add collision avoidance and viewport filtering, and use an offline
CONUS basemap whose license and storage cost are suitable for a Raspberry Pi image.

## Data publication and caching

`scripts/build_data.py` aggregates saved source rows by airport while retaining every provider
offer. It emits canonical JSON and a small `latest.json` manifest containing its byte count and
SHA-256. GitHub Raw applies HTTP compression while Git retains useful text deltas between daily
updates. The manifest is revalidated often;
the artifact is requested with `?v=<data_version>` so intermediary and service-worker caches do
not confuse two snapshots that use the stable v1 filename.

Data files are checked into GitHub so a deployment can obtain a specific commit without a live
data pipeline. Expansion to 48 states should preserve schema v1 where possible; incompatible
changes require new schema and artifact names.

Public clients fetch the verified data pair from GitHub on page load; Stratux clients retain their
packaged local copy.

## Stratux integration

The preferred integration path is to serve this directory under a distinct path such as
`/fuel-route/` from the existing Stratux HTTP server. The app should remain static and consume
the same files, avoiding another process on the Pi. A link can be added to the AngularJS
navigation first; a later native plate can reuse the JSON contract and Pi-hosted cache.

Stratux integration must account for service-worker scope and the common `http://192.168.10.1`
deployment. Browsers generally require HTTPS for service workers and Web Crypto except on
`localhost`; the current checksum-enforcing app therefore requires HTTPS (or localhost).
An HTTP-only receiver integration needs an explicitly designed, server-verified fallback and
cannot promise offline service-worker behavior.

## Stale data and NOTAM safety rules

- Always show `generated_at`, `notam_snapshot_at`, coverage, and a planning-only warning.
- Never present absence of a matching saved NOTAM as proof that fuel is currently available.
- Retain NOTAM-affected airports and full saved details in JSON for routes and auditability.
- Render an airport as a red warning marker rather than a normal fuel marker while
  `fuel_unavailable` is true. A route that explicitly contains it must retain that warning.
- Do not automatically clear a fuel-unavailable flag merely because a saved end time passed.
  Only a newly generated, attributable snapshot may change operational status.
- A failed source refresh retains that source's last known-good value and timestamp; a job with
  no successful source updates must not replace the last known-good cached package.
- Nationwide coverage must be explicitly measured; never infer 48-state completeness from a
  successful build or an airport count.
