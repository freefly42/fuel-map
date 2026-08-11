#!/usr/bin/env python3
"""Build the versioned fuel-airport package from the saved four-state snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

STATE_CODES = {"Arizona": "AZ", "New Mexico": "NM", "Nevada": "NV", "Texas": "TX"}
SCHEMA = "fuel-airports/v2"
LATEST_SCHEMA = "fuel-airports-latest/v1"
ARTIFACT_NAME = "fuel-airports-v2.json"
IDENTIFIER = re.compile(r"^[A-Z0-9]{2,4}$")
SOURCE_IDENTIFIER_FIXES = {
    "H": None,
    "L": None,
    "VH": None,
    "YUMA PROVING GROUND": "KLGF",
}


def text_or_none(value: str) -> str | None:
    value = value.strip()
    return value or None


def int_or_none(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def float_or_none(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def iso_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace(" UTC", "+00:00"))
    return parsed.isoformat().replace("+00:00", "Z")


def notam_timestamp(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H%MZ")
    return parsed.isoformat(timespec="seconds") + "Z"


def parse_notams(details: str) -> list[dict[str, str]]:
    notices = []
    for raw in filter(None, (item.strip() for item in details.split(" || "))):
        parts = raw.split(" | ", 2)
        if len(parts) != 3 or " to " not in parts[1]:
            notices.append({"raw": raw})
            continue
        starts_at, ends_at = parts[1].split(" to ", 1)
        notices.append(
            {
                "number": parts[0],
                "starts_at": notam_timestamp(starts_at),
                "ends_at": notam_timestamp(ends_at),
                "text": parts[2],
                "raw": raw,
            }
        )
    return notices


def first(rows: list[dict[str, str]], field: str) -> str:
    return next((row[field].strip() for row in rows if row[field].strip()), "")


def service_flags(rows: list[dict[str, str]]) -> dict[str, bool | None]:
    self_values = {row["self_service_100ll"].strip() for row in rows}
    service_values = {row["100ll_service"].strip() for row in rows}
    if any(value.startswith("Yes") for value in self_values):
        self_service: bool | None = True
    elif self_values == {"No indication"}:
        self_service = False
    else:
        self_service = None
    if any("full-service" in value.casefold() for value in service_values):
        full_service: bool | None = True
    elif service_values == {"Self-service indicated"}:
        full_service = False
    else:
        full_service = None
    return {
        "fuel_100ll": True,
        "self_service_100ll": self_service,
        "full_service_100ll": full_service,
    }


def fuel_24_hours(rows: list[dict[str, str]]) -> bool:
    details = " ".join(value for row in rows for field, value in row.items()
                       if "service" in field.casefold() or "additional" in field.casefold())
    return bool(re.search(r"\b(?:H24|24[\s-]*(?:HR|HOUR)S?)\b", details, re.I))


def build_airport(
    identifier: str,
    rows: list[dict[str, str]],
    coordinate_fallbacks: dict[str, list[float]],
) -> dict[str, Any]:
    rows.sort(key=lambda row: row["fbo"].casefold())
    notams = parse_notams(first(rows, "fuel_notam_details"))
    fuel_unavailable = any(
        "100LL" in notice.get("text", "") and "NOT AVBL" in notice.get("text", "")
        for notice in notams
    )
    offers = [
        {
            "provider": row["fbo"].strip(),
            "full_service_price_usd_per_gallon": float_or_none(row["100ll_full_price_usd_gal"]),
            "self_service_price_usd_per_gallon": float_or_none(row["100ll_self_price_usd_gal"]),
            "price_date": text_or_none(row["price_date"]),
            "price_age_days": int_or_none(row["price_age_days"]),
            "source_updated": text_or_none(row["source_updated"]),
            "source_url": text_or_none(row["source_url"]),
        }
        for row in rows
    ]
    latitude = float_or_none(first(rows, "latitude"))
    longitude = float_or_none(first(rows, "longitude"))
    if latitude is None or longitude is None:
        try:
            latitude, longitude = coordinate_fallbacks[identifier]
        except KeyError as error:
            raise ValueError(f"{identifier} has no coordinates") from error
        coordinate_source = "saved-faa-station-snapshot"
    else:
        coordinate_source = "csv"
    state = first(rows, "state")
    return {
        "id": identifier,
        "name": first(rows, "airport_name"),
        "city": first(rows, "city"),
        "state": state,
        "state_code": STATE_CODES[state],
        "position": {
            "latitude": latitude,
            "longitude": longitude,
            "source": coordinate_source,
        },
        "services": service_flags(rows),
        "deal_rating": 0,
        "fuel_24_hours": fuel_24_hours(rows),
        "fuel_24_hours_source": text_or_none(first(rows, "availability_source")),
        "fuel_unavailable": fuel_unavailable,
        "notams": notams,
        "offers": offers,
        "availability_source_url": text_or_none(first(rows, "availability_source")),
    }


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True, help="Directory containing the saved CSV and metadata snapshot")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parents[1] / "data")
    args = parser.parse_args()
    metadata = json.loads((args.source_dir / "100ll_prices_metadata.json").read_text(encoding="utf-8"))
    coordinate_fallbacks = json.loads(
        (Path(__file__).parents[1] / "source" / "coordinate-fallbacks.json").read_text(
            encoding="utf-8"
        )
    )
    with (args.source_dir / "100ll_prices_az_nm_nv_tx.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        source_identifier = row["airport_identifier"].strip()
        identifier = SOURCE_IDENTIFIER_FIXES.get(source_identifier, source_identifier)
        if identifier is None:
            continue
        if not IDENTIFIER.fullmatch(identifier):
            raise ValueError(f"invalid airport identifier: {source_identifier}")
        grouped[identifier].append(row)

    generated_at = iso_timestamp(metadata["retrieved_utc"])
    notam_snapshot_at = iso_timestamp(metadata["notam_searched_utc"])
    data_version = generated_at.replace("-", "").replace(":", "")
    airports = [
        build_airport(identifier, grouped[identifier], coordinate_fallbacks)
        for identifier in sorted(grouped)
    ]
    unavailable = sorted(airport["id"] for airport in airports if airport["fuel_unavailable"])
    states = [{"code": STATE_CODES[name], "name": name} for name in metadata["states"]]
    package = {
        "schema": SCHEMA,
        "schema_version": 2,
        "data_version": data_version,
        "generated_at": generated_at,
        "notam_snapshot_at": notam_snapshot_at,
        "coverage": {
            "scope": "partial-us-four-state-snapshot",
            "states": states,
            "airport_count": len(airports),
            "visible_fuel_marker_count": len(airports) - len(unavailable),
        },
        "sources": {
            "fuel": metadata["fuel_source"],
            "notams": metadata["notam_source"],
            "chart_supplement_effective": metadata["chart_supplement_effective"],
        },
        "airports": airports,
    }
    payload = canonical_json(package)
    digest = hashlib.sha256(payload).hexdigest()
    latest = {
        "schema": LATEST_SCHEMA,
        "schema_version": 1,
        "data_version": data_version,
        "generated_at": generated_at,
        "notam_snapshot_at": notam_snapshot_at,
        "artifact": {
            "path": ARTIFACT_NAME,
            "media_type": "application/json",
            "bytes": len(payload),
            "sha256": digest,
        },
        "coverage": package["coverage"],
    }
    excluded = sum(value is None for value in SOURCE_IDENTIFIER_FIXES.values())
    if len(airports) + excluded != metadata["airport_count"]:
        raise ValueError(f"metadata says {metadata['airport_count']} airports; generated {len(airports)}")
    if unavailable != sorted(metadata["airports_with_active_fuel_notams"]):
        raise ValueError(f"fuel-unavailable airports changed: {unavailable}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / ARTIFACT_NAME).write_bytes(payload)
    (args.output_dir / "latest.json").write_bytes(canonical_json(latest))
    print(f"wrote {len(airports)} airports, {len(airports) - len(unavailable)} visible markers, {len(payload)} JSON bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
