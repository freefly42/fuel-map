#!/usr/bin/env python3
"""Import open public-use airports from an FAA NASR APT CSV or ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            name = next(name for name in archive.namelist() if name.upper().endswith("APT_BASE.CSV"))
            text = io.TextIOWrapper(archive.open(name), encoding="utf-8-sig", newline="")
            return list(csv.DictReader(text))
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def has_100ll(row: dict[str, str]) -> bool:
    return "100LL" in {value.strip().upper() for value in row["FUEL_TYPES"].split(",")}


def airport_record(row: dict[str, str], previous: dict | None, effective: str) -> dict:
    fuel = has_100ll(row)
    airport = previous.copy() if previous else {
        "deal_rating": 0,
        "fuel_24_hours": None,
        "fuel_unavailable": False,
        "notams": [],
        "offers": [],
    }
    airport.update(
        id=row["ICAO_ID"].strip() or row["ARPT_ID"].strip(),
        faa_id=row["ARPT_ID"].strip(),
        name=row["ARPT_NAME"].strip().title(),
        city=row["CITY"].strip().title(),
        state=row["STATE_NAME"].strip().title(),
        state_code=row["STATE_CODE"].strip(),
        facility_use="public" if row["FACILITY_USE_CODE"] == "PU" else "restricted",
        position={
            "latitude": float(row["LAT_DECIMAL"]),
            "longitude": float(row["LONG_DECIMAL"]),
            "source": f"FAA NASR effective {effective}",
        },
    )
    services = dict(airport.get("services", {}))
    services["fuel_100ll"] = fuel
    airport["services"] = services
    if not fuel:
        services.update(self_service_100ll=False, full_service_100ll=False)
        airport.update(offers=[], deal_rating=0, fuel_24_hours=None,
                       availability_source_url=None)
        airport.pop("fuel_checked_at", None)
        airport.pop("fuel_24_hours_source", None)
    else:
        services.setdefault("self_service_100ll", None)
        services.setdefault("full_service_100ll", None)
        airport.setdefault("availability_source_url", NASR_URL)
    return airport


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apt", type=Path, help="FAA APT_BASE.csv or APT CSV ZIP")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    rows = [row for row in read_rows(args.apt)
            if row["COUNTRY_CODE"] == "US"
            and row["STATE_CODE"] in STATES
            and row["SITE_TYPE_CODE"] == "A"
            and row["ARPT_STATUS"] == "O"
            and (row["FACILITY_USE_CODE"] == "PU"
                 or row["FACILITY_USE_CODE"] == "PR" and has_100ll(row))]
    if not rows:
        raise ValueError("NASR input contained no open public-use airports")
    effective_dates = {row["EFF_DATE"] for row in rows}
    if len(effective_dates) != 1:
        raise ValueError(f"NASR input has multiple effective dates: {sorted(effective_dates)}")
    effective = next(iter(effective_dates)).replace("/", "-")
    data_dir = args.root / "data"
    package_path = data_dir / "fuel-airports-v2.json"
    package = json.loads(package_path.read_text())
    previous = {airport["id"]: airport for airport in package["airports"]}
    airports = [airport_record(row, previous.get(row["ICAO_ID"].strip() or row["ARPT_ID"].strip()), effective)
                for row in rows]
    airports.sort(key=lambda airport: airport["id"])
    identifiers = sorted(airport["id"] for airport in airports
                         if airport["facility_use"] == "public" and airport["services"]["fuel_100ll"])
    state_names = {row["STATE_CODE"]: row["STATE_NAME"].strip().title() for row in rows}
    package["airports"] = airports
    package["data_version"] = f"{package['data_version'].split('-nasr', 1)[0]}-nasr{effective.replace('-', '')}"
    package["coverage"] = {
        "scope": "all-50-states-open-public-use-and-restricted-fuel-airports",
        "states": [{"code": code, "name": state_names[code]} for code in sorted(STATES)],
        "airport_count": len(airports),
        "public_airport_count": sum(airport["facility_use"] == "public" for airport in airports),
        "restricted_airport_count": sum(airport["facility_use"] == "restricted" for airport in airports),
        "fuel_airport_count": sum(airport["services"]["fuel_100ll"] for airport in airports),
        "visible_fuel_marker_count": sum(
            airport["services"]["fuel_100ll"] and not airport["fuel_unavailable"]
            for airport in airports
        ),
    }
    package["sources"]["airports"] = f"FAA NASR APT data effective {effective}: {NASR_URL}"
    raw = json_bytes(package)
    latest_path = data_dir / "latest.json"
    latest = json.loads(latest_path.read_text())
    latest.update(data_version=package["data_version"], coverage=package["coverage"])
    latest["artifact"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    package_path.write_bytes(raw)
    latest_path.write_bytes(json_bytes(latest))
    (args.root / "config" / "airports.json").write_bytes(json_bytes(identifiers))
    print(f"imported {package['coverage']['public_airport_count']} public destinations and "
          f"{package['coverage']['restricted_airport_count']} restricted fuel airports in "
          f"{len(STATES)} states; queued {len(identifiers)} public airports advertising 100LL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
