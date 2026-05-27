"""
Utility portal CSV parser — Scope 2 electricity.

Choice justification (see DECISIONS.md):
We chose CSV portal export as the ingestion mode because:
  1. The majority of utility companies in India, UK, and US provide a
     "Download billing history" CSV from their portal (e.g., BESCOM, British Gas,
     Con Edison, PG&E). This requires no integration work on the client side.
  2. Utility APIs exist (e.g., Green Button / ESPI in the US, some BESCOM APIs)
     but are inconsistently implemented and often require utility-by-utility OAuth
     approval — not feasible for an enterprise with sites across multiple utilities.
  3. PDF bill parsing is possible (pdfplumber) but extremely brittle per-utility;
     CSV is far more stable.

Real-world utility CSV shapes researched:
  - BESCOM (Bangalore): Account No, Bill Month, Units Consumed (kWh),
    Bill Amount, Due Date — no demand charges broken out
  - PG&E (US): Start Date, End Date, Usage (kWh), Cost, Meter Number
  - British Gas (UK): Period Start, Period End, Gas Volume (m3),
    Electricity kWh, Tariff Rate
  - Con Edison (US): Invoice Date, Service Period Start/End,
    Electricity (kWh), Demand (kW), Amount Due

Common gotchas:
  - Billing periods don't align with calendar months (e.g. 17 Mar – 16 Apr)
  - Multi-meter accounts: one file has multiple meter_id rows
  - Units can be kWh, MWh, or even "units" (India, where 1 unit = 1 kWh)
  - Tariff structure (TOD, slab) is in the bill but we only care about kWh
"""

import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pandas as pd


# Canonical column map — handles the most common utility portal variants
COLUMN_ALIASES = {
    # Start of billing period
    "start_date": "period_start",
    "Start Date": "period_start",
    "Service Period Start": "period_start",
    "Period Start": "period_start",
    "Bill Month": "period_start",
    "Billing Period Start": "period_start",
    "From": "period_start",

    # End of billing period
    "end_date": "period_end",
    "End Date": "period_end",
    "Service Period End": "period_end",
    "Period End": "period_end",
    "To": "period_end",
    "Billing Period End": "period_end",

    # Consumption
    "Usage (kWh)": "kwh",
    "Electricity (kWh)": "kwh",
    "Units Consumed": "kwh",
    "units_consumed": "kwh",
    "kwh": "kwh",
    "kWh": "kwh",
    "usage_kwh": "kwh",
    "Consumption kWh": "kwh",

    # Meter
    "Meter Number": "meter_id",
    "Meter No": "meter_id",
    "Account No": "meter_id",
    "meter_id": "meter_id",

    # Site / facility
    "Site": "facility",
    "Location": "facility",
    "Address": "facility",
    "Facility": "facility",

    # Cost (informational, not used for emissions)
    "Cost": "cost",
    "Amount Due": "cost",
    "Bill Amount": "cost",
}


def parse_utility_date(val: str) -> Optional[date]:
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%b %Y", "%B %Y", "%Y%m", "%b-%Y"):
        try:
            from datetime import datetime
            d = datetime.strptime(val, fmt)
            # If only month/year, use first of month
            return d.date()
        except (ValueError, TypeError):
            continue
    return None


def kwh_from_value(val: str) -> Optional[Decimal]:
    """Parse kWh value — handle commas, spaces, 'MWh' labels."""
    val = str(val).strip().replace(",", "").replace(" ", "")
    # Strip any unit suffixes
    for suffix in ["kwh", "mwh", "kw", "units"]:
        if val.lower().endswith(suffix):
            val = val[: -len(suffix)].strip()
            break
    try:
        d = Decimal(val)
        return d
    except InvalidOperation:
        return None


# Emission factor keys by country — the analyst can override
COUNTRY_EF_MAP = {
    "IN": "electricity_kwh_in",
    "UK": "electricity_kwh_uk",
    "GB": "electricity_kwh_uk",
    "US": "electricity_kwh_us",
}


def process_utility_batch(file_obj, batch, organisation, reporting_year, emission_factors, country_code="IN"):
    from breathe_esg.apps.emissions.models import EmissionRecord

    raw = file_obj.read()
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return [], [{"row_index": None, "raw_data": "", "error_message": "Cannot decode file encoding."}]

    # Try CSV
    df = None
    for sep in [",", ";", "\t"]:
        try:
            candidate = pd.read_csv(io.StringIO(content), sep=sep, dtype=str, keep_default_na=False)
            if len(candidate.columns) >= 2:
                df = candidate
                break
        except Exception:
            continue

    if df is None:
        return [], [{"row_index": None, "raw_data": "", "error_message": "Cannot parse file as CSV."}]

    # Normalise column names
    df.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in df.columns}, inplace=True)

    if "kwh" not in df.columns:
        return [], [{
            "row_index": None,
            "raw_data": str(list(df.columns)),
            "error_message": f"No kWh column found. Detected columns: {list(df.columns)}",
        }]

    ef_key = COUNTRY_EF_MAP.get(country_code.upper(), "electricity_kwh_in")
    ef_value = Decimal(str(emission_factors.get(ef_key, 0.7082)))

    successes = []
    errors = []

    for idx, row in df.iterrows():
        row_dict = row.to_dict()
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

            # Hash for dedup: meter + period + kwh
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
