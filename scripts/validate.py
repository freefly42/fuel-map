#!/usr/bin/env python3
"""Validate the checked-in nationwide fuel package without third-party modules."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data"
EXPECTED_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
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
    assert published <= airports.keys() and len(published) >= 3000
    assert len(airports) >= 4500
    assert all(re.fullmatch(r"[A-Z0-9]{2,4}", identifier) for identifier in airports)
    assert all(re.fullmatch(r"[A-Z0-9]{2,4}", airport["faa_id"]) for airport in airports.values())
    assert EXPECTED_ROUTE <= airports.keys()
    assert EXPECTED_STATES == {airport["state_code"] for airport in airports.values()}
    assert all(airport.get("facility_use") in {"public", "restricted"} for airport in airports.values())
    assert all(airport["services"]["fuel_100ll"] for airport in airports.values()
               if airport["facility_use"] == "restricted")
    assert all(airports[identifier]["services"]["fuel_100ll"] for identifier in published)
    assert all(airport["deal_rating"] in {0, 1, 2} for airport in airports.values())
    assert any(airport["deal_rating"] == 2 for airport in airports.values())
    assert all(airport.get("fuel_24_hours") in {True, False, None} for airport in airports.values())
    averages = package["state_average_100ll_price_usd_per_gallon"]
    assert len(averages) == 48 and EXPECTED_STATES - {"AK", "HI"} <= averages.keys()
    assert not {"AK", "HI", "DC"} & averages.keys()
    assert all(isinstance(price, (int, float)) and price > 0 for price in averages.values())
    unavailable = {airport["id"] for airport in airports.values() if airport["fuel_unavailable"]}
    assert all(airports[identifier]["notams"] for identifier in unavailable)
    assert all(airport["fuel_unavailable"] == any(notice.get("active", True) for notice in airport["notams"])
               for airport in airports.values())
    assert all(not ("JET A" in notice["text"] and "100LL" not in notice["text"])
               for airport in airports.values() for notice in airport["notams"])
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
    visible = [airport for airport in airports.values()
               if airport["services"]["fuel_100ll"] and not airport["fuel_unavailable"]]
    assert package["coverage"]["airport_count"] == len(airports)
    assert package["coverage"]["public_airport_count"] == sum(
        airport["facility_use"] == "public" for airport in airports.values())
    assert package["coverage"]["restricted_airport_count"] == sum(
        airport["facility_use"] == "restricted" for airport in airports.values())
    assert package["coverage"]["fuel_airport_count"] == sum(
        airport["services"]["fuel_100ll"] for airport in airports.values())
    assert {state["code"] for state in package["coverage"]["states"]} == EXPECTED_STATES
    assert package["coverage"]["visible_fuel_marker_count"] == len(visible)
    assert latest["coverage"] == package["coverage"]
    print(f"validated pretty JSON, v2 data schema, "
          f"{package['coverage']['public_airport_count']} public airports, "
          f"{package['coverage']['restricted_airport_count']} restricted fuel airports, "
          f"{package['coverage']['fuel_airport_count']} advertising 100LL, and "
          f"{len(visible)} visible fuel markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
