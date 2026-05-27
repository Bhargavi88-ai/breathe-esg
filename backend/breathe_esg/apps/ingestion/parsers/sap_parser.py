"""
SAP parser — handles the flat-file / BAPI RFC extract format.
Uses Python's built-in csv module instead of pandas for deployment compatibility.
"""

import csv
import hashlib
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

SAP_UOM_MAP = {
    "L": ("litres", Decimal("1")),
    "LT": ("litres", Decimal("1")),
    "ML": ("litres", Decimal("0.001")),
    "M3": ("litres", Decimal("1000")),
    "GAL": ("litres", Decimal("3.78541")),
    "GL": ("litres", Decimal("3.78541")),
    "UK_GAL": ("litres", Decimal("4.54609")),
    "KG": ("kg", Decimal("1")),
    "G": ("kg", Decimal("0.001")),
    "T": ("kg", Decimal("1000")),
    "LB": ("kg", Decimal("0.453592")),
    "KWH": ("kwh", Decimal("1")),
    "MWH": ("kwh", Decimal("1000")),
    "GJ": ("kwh", Decimal("277.778")),
    "MMBTU": ("kwh", Decimal("293.071")),
    "BTU": ("kwh", Decimal("0.000293071")),
    "M3G": ("m3", Decimal("1")),
    "SCF": ("m3", Decimal("0.0283168")),
}

FUEL_PATTERNS = [
    (re.compile(r"diesel|gasoil|gas.?oil", re.I), "diesel_litre"),
    (re.compile(r"petrol|gasoline|benzin", re.I), "petrol_litre"),
    (re.compile(r"lpg|liquid.?petroleum|fl.?gas", re.I), "lpg_litre"),
    (re.compile(r"natural.?gas|erdgas|cng", re.I), "natural_gas_m3"),
    (re.compile(r"hsd|high.?speed.?diesel", re.I), "diesel_litre"),
]

COLUMN_ALIASES = {
    "MBLNR": "doc_number", "Materialbelegnummer": "doc_number",
    "MJAHR": "doc_year", "ZEILE": "line_item", "Pos": "line_item",
    "BUDAT": "posting_date", "Buchungsdatum": "posting_date",
    "WERKS": "plant_code", "Werk": "plant_code",
    "MATNR": "material_number", "Material": "material_number",
    "MAKTX": "material_desc", "Materialbezeichnung": "material_desc",
    "MENGE": "quantity", "Menge": "quantity",
    "MEINS": "uom", "Basismengeneinheit": "uom", "ME": "uom",
    "BWART": "movement_type", "Bewegungsart": "movement_type",
    "KOSTL": "cost_centre", "Kostenstelle": "cost_centre",
    "LIFNR": "vendor", "Lieferant": "vendor",
}


def parse_sap_date(val):
    val = str(val).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def infer_fuel_type(description):
    for pattern, factor_key in FUEL_PATTERNS:
        if pattern.search(description):
            return factor_key
    return None


def normalise_quantity(quantity, sap_uom):
    uom_upper = sap_uom.strip().upper()
    if uom_upper in SAP_UOM_MAP:
        norm_unit, factor = SAP_UOM_MAP[uom_upper]
        return quantity * factor, norm_unit
    return quantity, "unknown"


def read_csv_file(file_obj):
    """Read file and return list of dicts using csv module."""
    raw = file_obj.read()
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode file encoding.")

    # Try different delimiters
    for sep in ["\t", ";", ","]:
        try:
            reader = csv.DictReader(io.StringIO(content), delimiter=sep)
            rows = list(reader)
            if rows and len(rows[0]) >= 5:
                return rows
        except Exception:
            continue

    raise ValueError("Could not parse SAP file — check delimiter.")


def process_sap_batch(file_obj, batch, organisation, reporting_year, emission_factors):
    from breathe_esg.apps.emissions.models import EmissionRecord

    try:
        raw_rows = read_csv_file(file_obj)
    except ValueError as e:
        return [], [{"row_index": None, "raw_data": "", "error_message": str(e)}]

    if not raw_rows:
        return [], [{"row_index": None, "raw_data": "", "error_message": "File is empty."}]

    # Normalise column names
    def normalise_row(row):
        return {COLUMN_ALIASES.get(k, k): v for k, v in row.items()}

    rows = [normalise_row(r) for r in raw_rows]

    required = {"quantity", "uom", "material_desc"}
    first_keys = set(rows[0].keys())
    missing = required - first_keys
    if missing:
        return [], [{
            "row_index": None,
            "raw_data": str(list(first_keys)),
            "error_message": f"Missing required columns: {missing}. Got: {list(first_keys)}",
        }]

    successes = []
    errors = []

    for idx, row_dict in enumerate(rows):
        raw_repr = str(row_dict)
        try:
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

            fuel_key = infer_fuel_type(description)
            if fuel_key:
                category = EmissionRecord.CATEGORY_FUEL
                scope = EmissionRecord.SCOPE_1
            else:
                category = EmissionRecord.CATEGORY_PROCUREMENT
                scope = EmissionRecord.SCOPE_1

            norm_qty, norm_unit = normalise_quantity(qty, uom)

            ef_key = fuel_key
            ef_value = None
            kg_co2e = None

            if ef_key and ef_key in emission_factors:
                ef_value = Decimal(str(emission_factors[ef_key]))
                if norm_unit in ("litres", "m3", "kwh"):
                    kg_co2e = norm_qty * ef_value

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
