#!/usr/bin/env python3
"""Import a fuel-filtered FAA NOTAM Search XLS export into the data package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime, time
from pathlib import Path

ROOT = Path(__file__).parents[1]


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def affects_100ll(text: str) -> bool:
    text = text.upper()
    if "FUEL" not in text or not ("NOT AVBL" in text or "U/S" in text):
        return False
    other = "JET A" in text or "MOGAS" in text or "94 SWIFT" in text
    return not other or "100LL" in text or "AVGAS" in text


def active_at(text: str, starts: datetime, ends: datetime, checked: datetime) -> bool:
    if not starts <= checked <= ends:
        return False
    daily = re.search(r"\bDLY (\d{4})-(\d{4})\b", text)
    if not daily:
        return True
    start, end = (time(int(value[:2]), int(value[2:])) for value in daily.groups())
    current = checked.time()
    return start <= current <= end if start <= end else current >= start or current <= end


def parse_time(value: str) -> datetime:
    return datetime.strptime(value.removesuffix("EST"), "%m/%d/%Y %H%M").replace(tzinfo=UTC)


def read_export(path: Path) -> tuple[datetime, list[list[str]]]:
    try:
        import xlrd
    except ImportError as error:
        raise SystemExit("Reading legacy XLS requires xlrd") from error
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    title = str(sheet.cell_value(0, 0))
    checked = datetime.strptime(re.search(r"(\d{2}_\d{2}_\d{4}_\d{6})", title).group(1),
                                "%m_%d_%Y_%H%M%S").replace(tzinfo=UTC)
    return checked, [[str(sheet.cell_value(row, column)).strip()
                      for column in range(sheet.ncols)] for row in range(5, sheet.nrows)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xls", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    checked, rows = read_export(args.xls)
    data = args.root / "data"
    package_path = data / "fuel-airports-v2.json"
    package = json.loads(package_path.read_text())
    airports = {airport["id"]: airport for airport in package["airports"]}
    aliases: dict[str, dict[str, dict]] = {}
    for airport in airports.values():
        aliases.setdefault(airport["id"], {})[airport["id"]] = airport
        aliases.setdefault(airport.get("faa_id", airport["id"]), {})[airport["id"]] = airport
        airport["notams"] = []
        airport["fuel_unavailable"] = False
        airport["notam_checked_at"] = checked.isoformat().replace("+00:00", "Z")
    imported = active = 0
    for location, number, _class, _issued, effective, expiration, text in rows:
        matches = list(aliases.get(location.upper(), {}).values())
        if not affects_100ll(text) or len(matches) != 1:
            continue
        starts, ends = parse_time(effective), parse_time(expiration)
        is_active = active_at(text, starts, ends, checked)
        matches[0]["notams"].append({
            "number": number,
            "starts_at": starts.isoformat().replace("+00:00", "Z"),
            "ends_at": ends.isoformat().replace("+00:00", "Z"),
            "text": text,
            "active": is_active,
        })
        matches[0]["fuel_unavailable"] |= is_active
        imported += 1
        active += is_active
    package["notam_snapshot_at"] = checked.isoformat().replace("+00:00", "Z")
    package["sources"]["notams"] = "FAA NOTAM Search FUEL export, Aerodrome AD/SVC filters"
    package["coverage"]["visible_fuel_marker_count"] = sum(
        airport["services"]["fuel_100ll"] and not airport["fuel_unavailable"]
        for airport in airports.values())
    raw = json_bytes(package)
    package_path.write_bytes(raw)
    latest_path = data / "latest.json"
    latest = json.loads(latest_path.read_text())
    latest["notam_snapshot_at"] = package["notam_snapshot_at"]
    latest["coverage"] = package["coverage"]
    latest["artifact"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    latest_path.write_bytes(json_bytes(latest))
    print(f"imported {imported} 100LL-relevant NOTAMs; {active} active at {package['notam_snapshot_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
