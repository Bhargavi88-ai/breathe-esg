"""
Utility portal CSV parser — Scope 2 electricity.
Uses Python's built-in csv module instead of pandas.
"""

import csv
import hashlib
import io
from decimal import Decimal, InvalidOperation
from typing import Optional

COLUMN_ALIASES = {
    "start_date": "period_start", "Start Date": "period_start",
    "Service Period Start": "period_start", "Period Start": "period_start",
    "Bill Month": "period_start", "Billing Period Start": "period_start", "From": "period_start",
    "end_date": "period_end", "End Date": "period_end",
    "Service Period End": "period_end", "Period End": "period_end",
    "To": "period_end", "Billing Period End": "period_end",
    "Usage (kWh)": "kwh", "Electricity (kWh)": "kwh", "Units Consumed": "kwh",
    "units_consumed": "kwh", "kwh": "kwh", "kWh": "kwh",
    "usage_kwh": "kwh", "Consumption kWh": "kwh",
    "Meter Number": "meter_id", "Meter No": "meter_id",
    "Account No": "meter_id", "meter_id": "meter_id",
    "Site": "facility", "Location": "facility",
    "Address": "facility", "Facility": "facility",
    "Cost": "cost", "Amount Due": "cost", "Bill Amount": "cost",
}

COUNTRY_EF_MAP = {
    "IN": "electricity_kwh_in",
    "UK": "electricity_kwh_uk",
    "GB": "electricity_kwh_uk",
    "US": "electricity_kwh_us",
}


def parse_utility_date(val):
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%b %Y", "%B %Y", "%Y%m", "%b-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def kwh_from_value(val):
    val = str(val).strip().replace(",", "").replace(" ", "")
    for suffix in ["kwh", "mwh", "kw", "units"]:
        if val.lower().endswith(suffix):
            val = val[:-len(suffix)].strip()
            break
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def read_csv_file(file_obj):
    raw = file_obj.read()
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Cannot decode file encoding.")

    for sep in [",", ";", "\t"]:
        try:
            reader = csv.DictReader(io.StringIO(content), delimiter=sep)
            rows = list(reader)
            if rows and len(rows[0]) >= 2:
                return rows
        except Exception:
            continue
    raise ValueError("Cannot parse file as CSV.")


def process_utility_batch(file_obj, batch, organisation, reporting_year, emission_factors, country_code="IN"):
    from breathe_esg.apps.emissions.models import EmissionRecord

    try:
        raw_rows = read_csv_file(file_obj)
    except ValueError as e:
        return [], [{"row_index": None, "raw_data": "", "error_message": str(e)}]

    def normalise_row(row):
        return {COLUMN_ALIASES.get(k, k): v for k, v in row.items()}

    rows = [normalise_row(r) for r in raw_rows]

    if not rows or "kwh" not in rows[0]:
        cols = list(rows[0].keys()) if rows else []
        return [], [{
            "row_index": None,
            "raw_data": str(cols),
            "error_message": f"No kWh column found. Detected columns: {cols}",
        }]

    ef_key = COUNTRY_EF_MAP.get(country_code.upper(), "electricity_kwh_in")
    ef_value = Decimal(str(emission_factors.get(ef_key, 0.7082)))

    successes = []
    errors = []

    for idx, row_dict in enumerate(rows):
        raw_repr = str(row_dict)
        try:
            kwh = kwh_from_value(row_dict.get("kwh", ""))
            if kwh is None:
                raise ValueError(f"Cannot parse kWh value: {row_dict.get('kwh')}")
            if kwh <= 0:
                raise ValueError(f"Non-positive kWh ({kwh}), skipping.")

            period_start = parse_utility_date(row_dict.get("period_start", ""))
            period_end = parse_utility_date(row_dict.get("period_end", ""))
            meter_id = str(row_dict.get("meter_id", "")).strip()
            facility = str(row_dict.get("facility", "")).strip()
            kg_co2e = kwh * ef_value

            hash_input = f"{meter_id}{row_dict.get('period_start','')}{kwh}"
            row_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            successes.append({
                "source_type": EmissionRecord.SOURCE_UTILITY,
                "scope": EmissionRecord.SCOPE_2,
                "category": EmissionRecord.CATEGORY_ELECTRICITY,
                "sub_category": ef_key,
                "raw_quantity": kwh,
                "raw_unit": "kWh",
                "raw_description": f"Electricity consumption – meter {meter_id}",
                "normalised_quantity": kwh,
                "normalised_unit": "kwh",
                "emission_factor_key": ef_key,
                "emission_factor_value": ef_value,
                "kg_co2e": kg_co2e,
                "activity_date": period_start or period_end,
                "activity_period_start": period_start,
                "activity_period_end": period_end,
                "reporting_year": reporting_year,
                "facility_code": meter_id,
                "facility_name": facility,
                "country_code": country_code,
                "source_row_index": idx,
                "source_row_hash": row_hash,
                "extra": {
                    "meter_id": meter_id,
                    "cost": row_dict.get("cost", ""),
                    "ef_country": country_code,
                },
            })

        except Exception as e:
            errors.append({
                "row_index": idx,
                "raw_data": raw_repr[:1000],
                "error_message": str(e),
            })

    return successes, errors
