import csv
import hashlib
import io
import math
from decimal import Decimal, InvalidOperation
from typing import Optional

IATA_COORDS = {
    "DEL": (28.5665, 77.1031), "BOM": (19.0887, 72.8679),
    "BLR": (13.1986, 77.7066), "MAA": (12.9941, 80.1709),
    "HYD": (17.2403, 78.4294), "CCU": (22.6520, 88.4468),
    "DXB": (25.2532, 55.3657), "LHR": (51.4700, -0.4543),
    "CDG": (49.0097, 2.5479), "FRA": (50.0333, 8.5706),
    "AMS": (52.3086, 4.7639), "JFK": (40.6413, -73.7781),
    "ORD": (41.9742, -87.9073), "SFO": (37.6213, -122.3790),
    "LAX": (33.9425, -118.4081), "SIN": (1.3644, 103.9915),
    "HKG": (22.3080, 113.9185), "NRT": (35.7720, 140.3929),
    "SYD": (-33.9461, 151.1772), "DUB": (53.4213, -6.2700),
    "ZRH": (47.4647, 8.5492), "MUC": (48.3537, 11.7750),
    "MAD": (40.4936, -3.5668), "BCN": (41.2974, 2.0833),
    "GVA": (46.2380, 6.1089), "BRU": (50.9014, 4.4844),
    "CPH": (55.6180, 12.6508), "OSL": (60.1939, 11.1004),
    "ARN": (59.6519, 17.9186), "HEL": (60.3172, 24.9633),
}

TRAVEL_COLUMN_ALIASES = {
    "Transaction Date": "travel_date", "Expense Type": "travel_type",
    "From City": "origin", "To City": "destination",
    "Departure Airport": "origin_iata", "Arrival Airport": "destination_iata",
    "Miles": "distance", "KM": "distance_km", "Distance (km)": "distance_km",
    "Flight Class": "cabin_class", "Hotel Nights": "hotel_nights",
    "Hotel City": "hotel_city", "Employee Email": "traveler_email",
    "trip_id": "trip_id", "travel_type": "travel_type",
    "departure_date": "travel_date", "origin_iata": "origin_iata",
    "destination_iata": "destination_iata", "cabin_class": "cabin_class",
    "distance_km": "distance_km", "hotel_nights": "hotel_nights",
    "hotel_city": "hotel_city", "traveler_email": "traveler_email",
}

FLIGHT_TYPES = {"airfare", "flight", "air", "air travel", "flights"}
HOTEL_TYPES = {"hotel", "lodging", "accommodation"}
GROUND_TYPES = {"car rental", "taxi", "car", "ground", "ground transport", "rental car", "rideshare"}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def distance_from_iata(origin, dest):
    origin, dest = origin.strip().upper(), dest.strip().upper()
    if origin in IATA_COORDS and dest in IATA_COORDS:
        lat1, lon1 = IATA_COORDS[origin]
        lat2, lon2 = IATA_COORDS[dest]
        return haversine_km(lat1, lon1, lat2, lon2)
    return None


def flight_ef_key(distance_km):
    if distance_km < 500:
        return "flight_domestic_pkm"
    elif distance_km <= 3700:
        return "flight_short_haul_pkm"
    else:
        return "flight_long_haul_pkm"


def parse_travel_date(val):
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%b %d, %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
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
        raise ValueError("Cannot decode file.")

    for sep in [",", ";", "\t"]:
        try:
            reader = csv.DictReader(io.StringIO(content), delimiter=sep)
            rows = list(reader)
            if rows and len(rows[0]) >= 2:
                return rows
        except Exception:
            continue
    raise ValueError("Cannot parse file.")


def process_travel_batch(file_obj, batch, organisation, reporting_year, emission_factors):
    from breathe_esg.apps.emissions.models import EmissionRecord

    try:
        raw_rows = read_csv_file(file_obj)
    except ValueError as e:
        return [], [{"row_index": None, "raw_data": "", "error_message": str(e)}]

    def normalise_row(row):
        return {TRAVEL_COLUMN_ALIASES.get(k, k): v for k, v in row.items()}

    rows = [normalise_row(r) for r in raw_rows]

    if not rows or "travel_type" not in rows[0]:
        cols = list(rows[0].keys()) if rows else []
        return [], [{
            "row_index": None,
            "raw_data": str(cols),
            "error_message": f"No travel_type column. Got: {cols}",
        }]

    successes = []
    errors = []

    for idx, row_dict in enumerate(rows):
        raw_repr = str(row_dict)
        try:
            travel_type_raw = str(row_dict.get("travel_type", "")).strip().lower()
            travel_date = parse_travel_date(row_dict.get("travel_date", ""))

            if travel_type_raw in FLIGHT_TYPES:
                dist_km = None
                for col in ["distance_km", "distance"]:
                    raw_d = str(row_dict.get(col, "")).strip().replace(",", "")
                    if raw_d:
                        try:
                            dist_km = float(Decimal(raw_d))
                            if col == "distance":
                                dist_km = dist_km * 1.60934
                            break
                        except Exception:
                            pass

                if dist_km is None:
                    origin_iata = str(row_dict.get("origin_iata", "")).strip().upper()
                    dest_iata = str(row_dict.get("destination_iata", "")).strip().upper()
                    if origin_iata and dest_iata:
                        dist_km = distance_from_iata(origin_iata, dest_iata)

                if dist_km is None:
                    raise ValueError("Cannot determine flight distance.")

                cabin = str(row_dict.get("cabin_class", "economy")).strip()
                ef_key = flight_ef_key(dist_km)
                ef_val = Decimal(str(emission_factors.get(ef_key, 0.1950)))

                multiplier = Decimal("1.0")
                if "business" in cabin.lower():
                    multiplier = Decimal("2.0")
                elif "first" in cabin.lower():
                    multiplier = Decimal("2.4")

                dist_decimal = Decimal(str(round(dist_km, 2)))
                kg_co2e = dist_decimal * ef_val * multiplier

                hash_input = f"flight{row_dict.get('traveler_email','')}{row_dict.get('origin_iata','')}{row_dict.get('destination_iata','')}{travel_date}"
                row_hash = hashlib.sha256(hash_input.encode()).hexdigest()

                successes.append({
                    "source_type": EmissionRecord.SOURCE_TRAVEL,
                    "scope": EmissionRecord.SCOPE_3,
                    "category": EmissionRecord.CATEGORY_FLIGHT,
                    "sub_category": cabin,
                    "raw_quantity": dist_decimal,
                    "raw_unit": "km",
                    "raw_description": f"Flight {row_dict.get('origin_iata','')}→{row_dict.get('destination_iata','')} ({cabin})",
                    "normalised_quantity": dist_decimal,
                    "normalised_unit": "km",
                    "emission_factor_key": ef_key,
                    "emission_factor_value": ef_val,
                    "kg_co2e": kg_co2e,
                    "activity_date": travel_date,
                    "reporting_year": reporting_year,
                    "source_row_index": idx,
                    "source_row_hash": row_hash,
                    "extra": {
                        "traveler": row_dict.get("traveler_email", ""),
                        "origin_iata": row_dict.get("origin_iata", ""),
                        "dest_iata": row_dict.get("destination_iata", ""),
                        "cabin": cabin,
                        "class_multiplier": str(multiplier),
                    },
                })

            elif travel_type_raw in HOTEL_TYPES:
                nights_raw = str(row_dict.get("hotel_nights", "1")).strip()
                try:
                    nights = Decimal(nights_raw)
                    if nights <= 0:
                        raise ValueError("Non-positive nights.")
                except InvalidOperation:
                    raise ValueError(f"Invalid hotel nights: {nights_raw}")

                ef_key = "hotel_night"
                ef_val = Decimal(str(emission_factors.get(ef_key, 31.0)))
                kg_co2e = nights * ef_val
                hotel_city = str(row_dict.get("hotel_city", "")).strip()

                hash_input = f"hotel{row_dict.get('traveler_email','')}{hotel_city}{travel_date}{nights}"
                row_hash = hashlib.sha256(hash_input.encode()).hexdigest()

                successes.append({
                    "source_type": EmissionRecord.SOURCE_TRAVEL,
                    "scope": EmissionRecord.SCOPE_3,
                    "category": EmissionRecord.CATEGORY_HOTEL,
                    "sub_category": hotel_city,
                    "raw_quantity": nights,
                    "raw_unit": "nights",
                    "raw_description": f"Hotel stay – {hotel_city} ({nights} nights)",
                    "normalised_quantity": nights,
                    "normalised_unit": "nights",
                    "emission_factor_key": ef_key,
                    "emission_factor_value": ef_val,
                    "kg_co2e": kg_co2e,
                    "activity_date": travel_date,
                    "reporting_year": reporting_year,
                    "source_row_index": idx,
                    "source_row_hash": row_hash,
                    "extra": {
                        "traveler": row_dict.get("traveler_email", ""),
                        "hotel_city": hotel_city,
                        "nights": str(nights),
                    },
                })

            elif travel_type_raw in GROUND_TYPES:
                dist_km = None
                for col in ["distance_km", "distance"]:
                    raw_d = str(row_dict.get(col, "")).strip().replace(",", "")
                    if raw_d:
                        try:
                            dist_km = Decimal(raw_d)
                            break
                        except Exception:
                            pass

                if dist_km is None:
                    dist_km = Decimal("20")

                ef_key = "taxi_km"
                ef_val = Decimal(str(emission_factors.get(ef_key, 0.1489)))
                kg_co2e = dist_km * ef_val

                hash_input = f"ground{row_dict.get('traveler_email','')}{travel_date}{dist_km}"
                row_hash = hashlib.sha256(hash_input.encode()).hexdigest()

                successes.append({
                    "source_type": EmissionRecord.SOURCE_TRAVEL,
                    "scope": EmissionRecord.SCOPE_3,
                    "category": EmissionRecord.CATEGORY_GROUND,
                    "sub_category": travel_type_raw,
                    "raw_quantity": dist_km,
                    "raw_unit": "km",
                    "raw_description": f"Ground transport – {travel_type_raw}",
                    "normalised_quantity": dist_km,
                    "normalised_unit": "km",
                    "emission_factor_key": ef_key,
                    "emission_factor_value": ef_val,
                    "kg_co2e": kg_co2e,
                    "activity_date": travel_date,
                    "reporting_year": reporting_year,
                    "source_row_index": idx,
                    "source_row_hash": row_hash,
                    "extra": {
                        "traveler": row_dict.get("traveler_email", ""),
                        "transport_type": travel_type_raw,
                    },
                })

            else:
                raise ValueError(f"Unknown travel type: '{travel_type_raw}'")

        except Exception as e:
            errors.append({
                "row_index": idx,
                "raw_data": raw_repr[:1000],
                "error_message": str(e),
            })

    return successes, errors
