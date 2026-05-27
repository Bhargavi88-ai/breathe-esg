"""
SAP parser — handles the flat-file / BAPI RFC extract format.

Choice justification (see DECISIONS.md):
We chose the SAP flat-file RFC extract (sometimes called a BAPI extract or
MATDOC/MSEG extract) because:
  1. It's the lowest-common-denominator export any SAP ECC / S/4HANA system
     can produce without add-ons — it's a delimiter-separated text dump.
  2. IDoc XML is richer but requires EDI infrastructure we won't assume clients have.
  3. OData services are cleaner but require a live system connection; clients
     typically share snapshots, not live API access, for compliance reasons.

Real SAP flat files we researched:
  - Movement type 201/261 (goods issue to cost centre) — fuel & consumables
  - Movement type 501 (receipt without PO) — not relevant, skipped
  - Plant codes (WERKS) are 4-char alphanumeric; we maintain a lookup table in `extra`
  - Dates are YYYYMMDD (BUDAT / BLDAT)
  - Quantities can be in any UoM registered in SAP; we handle the common ones
  - German column headers appear when the system locale isn't overridden

Column mapping (SAP MSEG-based):
  MBLNR  - Material document number
  MJAHR  - Material document year
  ZEILE  - Line item
  BUDAT  - Posting date (YYYYMMDD)
  WERKS  - Plant code
  MATNR  - Material number
  MAKTX  - Material description (can be in German)
  MENGE  - Quantity
  MEINS  - Unit of measure (SAP UoM codes, e.g. L, GAL, M3, KG)
  BWART  - Movement type
  KOSTL  - Cost centre
  LIFNR  - Vendor number (for procurement)
"""

import hashlib
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pandas as pd

# SAP UoM → (normalised unit, conversion factor to that unit)
# Factor means: 1 SAP unit = factor * normalised unit
SAP_UOM_MAP = {
    # Volume — normalise to litres
    "L": ("litres", Decimal("1")),
    "LT": ("litres", Decimal("1")),
    "ML": ("litres", Decimal("0.001")),
    "M3": ("litres", Decimal("1000")),
    "GAL": ("litres", Decimal("3.78541")),  # US gallon
    "GL": ("litres", Decimal("3.78541")),
    "UK_GAL": ("litres", Decimal("4.54609")),  # Imperial gallon
    # Mass — normalise to kg
    "KG": ("kg", Decimal("1")),
    "G": ("kg", Decimal("0.001")),
    "T": ("kg", Decimal("1000")),
    "LB": ("kg", Decimal("0.453592")),
    # Energy — normalise to kWh
    "KWH": ("kwh", Decimal("1")),
    "MWH": ("kwh", Decimal("1000")),
    "GJ": ("kwh", Decimal("277.778")),
    "MMBTU": ("kwh", Decimal("293.071")),
    "BTU": ("kwh", Decimal("0.000293071")),
    # Gas volume — normalise to m³
    "M3G": ("m3", Decimal("1")),
    "SCF": ("m3", Decimal("0.0283168")),
}

# Movement types that imply fuel consumption (Scope 1)
FUEL_MOVEMENT_TYPES = {"201", "261", "262"}

# Fuel material description patterns (regex, case-insensitive)
FUEL_PATTERNS = [
    (re.compile(r"diesel|gasoil|gas.?oil", re.I), "diesel_litre"),
    (re.compile(r"petrol|gasoline|benzin", re.I), "petrol_litre"),
    (re.compile(r"lpg|liquid.?petroleum|fl.?gas", re.I), "lpg_litre"),
    (re.compile(r"natural.?gas|erdgas|cng", re.I), "natural_gas_m3"),
    (re.compile(r"hsd|high.?speed.?diesel", re.I), "diesel_litre"),
]


def parse_sap_date(val: str) -> Optional[date]:
    """SAP dates are YYYYMMDD. Fall back to common alternatives."""
    val = str(val).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def infer_fuel_type(description: str) -> Optional[str]:
    for pattern, factor_key in FUEL_PATTERNS:
        if pattern.search(description):
            return factor_key
    return None


def normalise_quantity(quantity: Decimal, sap_uom: str):
    """
    Returns (normalised_quantity, normalised_unit) or (quantity, 'unknown').
    """
    uom_upper = sap_uom.strip().upper()
    if uom_upper in SAP_UOM_MAP:
        norm_unit, factor = SAP_UOM_MAP[uom_upper]
        return quantity * factor, norm_unit
    return quantity, "unknown"


def parse_sap_file(file_obj, encoding="utf-8") -> pd.DataFrame:
    """
    Read the SAP flat file. Try tab, semicolon, comma delimiters.
    Handle BOM (SAP sometimes writes UTF-8 BOM files on Windows).
    """
    raw = file_obj.read()

    # Try to detect encoding
    for enc in [encoding, "utf-8-sig", "latin-1", "cp1252"]:
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode file — try UTF-8 or Latin-1.")

    # Try different delimiters
    for sep in ["\t", ";", ","]:
        try:
            df = pd.read_csv(io.StringIO(content), sep=sep, dtype=str, keep_default_na=False)
            if len(df.columns) >= 5:
                return df
        except Exception:
            continue

    raise ValueError("Could not parse SAP file — check delimiter (expected tab, semicolon, or comma).")


# Mapping from common SAP column name variants (including German) to canonical names
COLUMN_ALIASES = {
    "MBLNR": "doc_number",
    "Materialbelegnummer": "doc_number",
    "MJAHR": "doc_year",
    "ZEILE": "line_item",
    "Pos": "line_item",
    "BUDAT": "posting_date",
    "Buchungsdatum": "posting_date",
    "WERKS": "plant_code",
    "Werk": "plant_code",
    "MATNR": "material_number",
    "Material": "material_number",
    "MAKTX": "material_desc",
    "Materialbezeichnung": "material_desc",
    "MENGE": "quantity",
    "Menge": "quantity",
    "MEINS": "uom",
    "Basismengeneinheit": "uom",
    "ME": "uom",
    "BWART": "movement_type",
    "Bewegungsart": "movement_type",
    "KOSTL": "cost_centre",
    "Kostenstelle": "cost_centre",
    "LIFNR": "vendor",
    "Lieferant": "vendor",
}


def process_sap_batch(file_obj, batch, organisation, reporting_year, emission_factors):
    """
    Main entry point. Returns (successes, errors) as lists of dicts.
    successes: dicts ready to build EmissionRecord
    errors: dicts ready to build IngestionError
    """
    from breathe_esg.apps.emissions.models import EmissionRecord

    try:
        df = parse_sap_file(file_obj)
    except ValueError as e:
        return [], [{"row_index": None, "raw_data": "", "error_message": str(e)}]

    # Normalise column names
    df.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in df.columns}, inplace=True)

    required = {"quantity", "uom", "material_desc"}
    missing = required - set(df.columns)
    if missing:
        return [], [{
            "row_index": None,
            "raw_data": str(list(df.columns)),
            "error_message": f"Missing required columns: {missing}. Got: {list(df.columns)}",
        }]

    successes = []
    errors = []

    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        raw_repr = str(row_dict)

        try:
            # Quantity
            try:
                qty = Decimal(str(row_dict.get("quantity", "")).replace(",", ".").strip())
            except InvalidOperation:
                raise ValueError(f"Invalid quantity: {row_dict.get('quantity')}")

            if qty <= 0:
                raise ValueError(f"Non-positive quantity ({qty}), skipping.")

            uom = str(row_dict.get("uom", "")).strip().upper()
            description = str(row_dict.get("material_desc", "")).strip()
            posting_date = parse_sap_date(row_dict.get("posting_date", ""))
            plant_code = str(row_dict.get("plant_code", "")).strip()
            movement_type = str(row_dict.get("movement_type", "")).strip()

            # Determine if this is fuel or procurement
            fuel_key = infer_fuel_type(description)
            if fuel_key:
                category = EmissionRecord.CATEGORY_FUEL
                scope = EmissionRecord.SCOPE_1
            else:
                category = EmissionRecord.CATEGORY_PROCUREMENT
                scope = EmissionRecord.SCOPE_1  # Scope 1 if combustion on-site

            # Normalise quantity
            norm_qty, norm_unit = normalise_quantity(qty, uom)

            # Get emission factor
            ef_key = fuel_key
            ef_value = None
            kg_co2e = None

            if ef_key and ef_key in emission_factors:
                ef_value = Decimal(str(emission_factors[ef_key]))
                # Convert to the right base for the factor
                if norm_unit == "litres":
                    kg_co2e = norm_qty * ef_value
                elif norm_unit == "m3":
                    kg_co2e = norm_qty * ef_value
                elif norm_unit == "kwh":
                    kg_co2e = norm_qty * ef_value

            # Build row hash for dedup
            hash_input = f"{row_dict.get('doc_number','')}{row_dict.get('line_item','')}{qty}{uom}{description}"
            row_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            successes.append({
                "source_type": EmissionRecord.SOURCE_SAP,
                "scope": scope,
                "category": category,
                "sub_category": fuel_key or "non-fuel",
                "raw_quantity": qty,
                "raw_unit": uom,
                "raw_description": description,
                "normalised_quantity": norm_qty,
                "normalised_unit": norm_unit,
                "emission_factor_key": ef_key or "",
                "emission_factor_value": ef_value,
                "kg_co2e": kg_co2e,
                "activity_date": posting_date,
                "reporting_year": reporting_year,
                "facility_code": plant_code,
                "source_row_index": idx,
                "source_row_hash": row_hash,
                "extra": {
                    "doc_number": row_dict.get("doc_number", ""),
                    "movement_type": movement_type,
                    "cost_centre": row_dict.get("cost_centre", ""),
                    "vendor": row_dict.get("vendor", ""),
                    "material_number": row_dict.get("material_number", ""),
                },
            })

        except Exception as e:
            errors.append({
                "row_index": idx,
                "raw_data": raw_repr[:1000],
                "error_message": str(e),
            })

    return successes, errors
