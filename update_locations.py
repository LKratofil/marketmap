#!/usr/bin/env python3
"""Geocode location dataset using US Census batch API with Nominatim fallbacks."""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import string
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_SINGLE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "marketmap-fix/1.0 (example@example.com)"
CENSUS_SLEEP = 0.2
NOMINATIM_SLEEP = 1.2

AddressKey = Tuple[str, str, str, str]


def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    row = dict(row)
    if "\ufeffRegion" in row:
        row["Region"] = row.pop("\ufeffRegion")
    return row


def build_address_key(row: Dict[str, str]) -> AddressKey:
    addr1 = row["Address Line 1"].strip()
    city = row["City"].strip()
    state = row["State"].strip()
    zip_code = row["Zip"].strip()
    zip_fmt = zip_code.zfill(5) if zip_code.isdigit() else zip_code
    address_field = addr1 if addr1 else city
    return (
        address_field.upper(),
        city.upper(),
        state.upper(),
        zip_fmt,
    )


def make_unique_records(rows: Iterable[Dict[str, str]]) -> Tuple[Dict[AddressKey, str], List[Dict[str, str]]]:
    mapping: Dict[AddressKey, str] = OrderedDict()
    records: List[Dict[str, str]] = []
    for row in rows:
        key = build_address_key(row)
        if key not in mapping:
            uid = f"ID{len(mapping) + 1}"
            mapping[key] = uid
            addr1 = row["Address Line 1"].strip()
            city = row["City"].strip()
            state = row["State"].strip()
            zip_code = row["Zip"].strip()
            zip_fmt = zip_code.zfill(5) if zip_code.isdigit() else zip_code
            records.append({
                "id": uid,
                "address": addr1 if addr1 else city,
                "city": city,
                "state": state,
                "zip": zip_fmt,
            })
    return mapping, records


def census_batch_geocode(records: List[Dict[str, str]]) -> Dict[str, Tuple[float | None, float | None]]:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", "address", "city", "state", "zip"])
    for record in records:
        writer.writerow([record["id"], record["address"], record["city"], record["state"], record["zip"]])
    csv_payload = output.getvalue()

    boundary = "----WebKitFormBoundary" + "".join(random.choices(string.ascii_letters + string.digits, k=16))
    parts = []
    for name, value in (("benchmark", "Public_AR_Current"), ("returntype", "locations")):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"addressFile\"; filename=\"addresses.csv\"\r\n"
        f"Content-Type: text/csv\r\n\r\n{csv_payload}\r\n"
    )
    parts.append(f"--{boundary}--\r\n")
    body = "".join(parts).encode("utf-8")

    headers = {"User-Agent": USER_AGENT, "Content-Type": f"multipart/form-data; boundary={boundary}"}
    response = _rate_limited_request(CENSUS_BATCH_URL, data=body, headers=headers, sleep=CENSUS_SLEEP)
    reader = csv.reader(io.StringIO(response.decode("utf-8")))
    results: Dict[str, Tuple[float | None, float | None]] = {}
    for row in reader:
        if not row:
            continue
        uid = row[0]
        if uid == "id":
            continue
        status = row[2]
        coord_str = row[5] if len(row) > 5 else ""
        lat = lon = None
        if status == "Match" and coord_str:
            try:
                lon_str, lat_str = coord_str.split(",")
                lon = float(lon_str)
                lat = float(lat_str)
            except Exception:
                lat = lon = None
        results[uid] = (lat, lon)
    return results


def nominatim_geocode(query: str) -> Tuple[float | None, float | None]:
    params = urllib.parse.urlencode({"format": "json", "q": query, "limit": 1})
    url = f"{NOMINATIM_URL}?{params}"
    headers = {"User-Agent": USER_AGENT}
    response = _rate_limited_request(url, headers=headers, sleep=NOMINATIM_SLEEP)
    data = json.loads(response.decode("utf-8"))
    if data:
        try:
            return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            return None, None
    return None, None


def _rate_limited_request(url: str, data: bytes | None = None, method: str = "GET", headers: Dict[str, str] | None = None, sleep: float = 0.0) -> bytes:
    if headers is None:
        headers = {}
    if sleep > 0:
        time.sleep(sleep)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def geocode_dataset(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, object]], List[Dict[str, str]]]:
    mapping, records = make_unique_records(rows)
    results = census_batch_geocode(records)

    missing = [rec for rec in records if results.get(rec["id"], (None, None))[0] is None]
    for idx, record in enumerate(missing, start=1):
        addr1 = record["address"]
        city = record["city"]
        state = record["state"]
        zip_code = record["zip"]
        queries = []
        if addr1:
            queries.append(", ".join(filter(None, [addr1, city, state, zip_code])))
        if zip_code:
            queries.append(f"{city}, {state} {zip_code}")
        queries.append(f"{city}, {state}")
        lat = lon = None
        for query in queries:
            lat, lon = nominatim_geocode(query)
            if lat is not None and lon is not None:
                break
        results[record["id"]] = (lat, lon)

    failures: List[Dict[str, str]] = []
    updated_rows: List[Dict[str, object]] = []
    for original in rows:
        key = build_address_key(original)
        uid = mapping[key]
        lat, lon = results.get(uid, (None, None))
        row_out: Dict[str, object] = dict(original)
        if lat is None or lon is None:
            failures.append({
                "Location Code": original["Location Code"],
                "City": original["City"],
                "State": original["State"],
                "Zip": original["Zip"],
            })
            row_out["Latitude"] = ""
            row_out["Longitude"] = ""
            row_out["Location"] = ""
        else:
            row_out["Latitude"] = lat
            row_out["Longitude"] = lon
            row_out["Location"] = f"{lat},{lon}"
        updated_rows.append(row_out)
    return updated_rows, failures


def write_outputs(rows: List[Dict[str, object]], output_csv: Path, output_json: Path) -> None:
    fieldnames = [
        "Region",
        "Location Code",
        "Location Name",
        "Address Line 1",
        "City",
        "State",
        "Zip",
        "County",
        "Phone",
        "Line of Business",
        "Division",
        "Division Region",
        "Area",
        "Senior Vice President",
        "Area Manager",
        "General Manager",
        "Email Address",
        "MSA Name",
        "Latitude",
        "Longitude",
        "Location",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    with output_json.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("Location List Oct 2025.csv"), help="Input CSV path")
    parser.add_argument("--output-csv", type=Path, default=Path("Location List Oct 2025 with locations.csv"), help="Output CSV path")
    parser.add_argument("--output-json", type=Path, default=Path("data_with_locations.json"), help="Output JSON path")
    parser.add_argument("--failures", type=Path, default=Path("geocoding_failures.json"), help="Where to record unresolved rows")
    args = parser.parse_args()

    with args.input.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [normalize_row(row) for row in reader]

    updated_rows, failures = geocode_dataset(rows)
    write_outputs(updated_rows, args.output_csv, args.output_json)

    with args.failures.open("w", encoding="utf-8") as f:
        json.dump(failures, f, indent=2)

    print(f"Processed {len(updated_rows)} rows; failures: {len(failures)}")


if __name__ == "__main__":
    main()
