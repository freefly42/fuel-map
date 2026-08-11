#!/usr/bin/env python3
"""Validate the checked-in four-state fuel package without third-party modules."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data"
EXPECTED_STATES = {"AZ", "NM", "NV", "TX"}
EXPECTED_ROUTE = {"KHND", "KSJN", "KIWS"}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def main() -> int:
    latest = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    raw = (DATA / latest["artifact"]["path"]).read_bytes()
    package = json.loads(raw)
    assert latest["schema"] == "fuel-airports-latest/v1"
    assert latest["schema_version"] == 1
    assert package["schema"] == "fuel-airports/v2"
    assert package["schema_version"] == 2
    assert b"airnav" not in raw.lower()
    assert package["data_version"] == latest["data_version"]
    assert raw == canonical_json(package), "payload is not canonical JSON"
    assert hashlib.sha256(raw).hexdigest() == latest["artifact"]["sha256"]
    assert len(raw) == latest["artifact"]["bytes"]
    airports = {airport["id"]: airport for airport in package["airports"]}
    published = set(json.loads((ROOT / "config" / "airports.json").read_text()))
    assert published <= airports.keys() and len(published) == 364
    assert all(re.fullmatch(r"[A-Z0-9]{2,4}", identifier) for identifier in airports)
    assert EXPECTED_ROUTE <= airports.keys()
    assert EXPECTED_STATES <= {airport["state_code"] for airport in airports.values()}
    assert not {"AK", "HI"} & {airport["state_code"] for airport in airports.values()}
    assert all(airport["deal_rating"] in {0, 1, 2} for airport in airports.values())
    assert any(airport["deal_rating"] == 2 for airport in airports.values())
    assert all(airport.get("fuel_24_hours") in {True, False, None} for airport in airports.values())
    averages = package["state_average_100ll_price_usd_per_gallon"]
    assert len(averages) == 48 and EXPECTED_STATES <= averages.keys()
    assert not {"AK", "HI", "DC"} & averages.keys()
    assert all(isinstance(price, (int, float)) and price > 0 for price in averages.values())
    unavailable = {airport["id"] for airport in airports.values() if airport["fuel_unavailable"]}
    assert all(airports[identifier]["notams"] for identifier in unavailable)
    assert all(
        "notam_checked_at" not in airport
        or datetime.fromisoformat(airport["notam_checked_at"].replace("Z", "+00:00"))
        for airport in airports.values()
    )
    assert all(
        "fuel_checked_at" not in airport
        or datetime.fromisoformat(airport["fuel_checked_at"].replace("Z", "+00:00"))
        for airport in airports.values()
    )
    visible = [airport for airport in airports.values() if not airport["fuel_unavailable"]]
    assert package["coverage"]["visible_fuel_marker_count"] == len(visible)
    assert latest["coverage"] == package["coverage"]
    print(f"validated pretty JSON, v2 data schema, 364 published four-state airports, "
          f"{len(airports) - len(published)} additional deal airports, and {len(visible)} visible markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
