"""
Management command: python manage.py seed_demo

Creates:
  - Demo organisation "Acme Manufacturing Ltd"
  - Admin user: admin@acme.com / password: demo1234
  - Analyst user: analyst@acme.com / password: demo1234
  - ~80 realistic emission records across all three sources
"""
import io
import csv
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.conf import settings

from breathe_esg.apps.accounts.models import Organisation, User
from breathe_esg.apps.ingestion.models import IngestionBatch
from breathe_esg.apps.ingestion.service import run_ingestion


DEMO_ORG_NAME = "Acme Manufacturing Ltd"
DEMO_ORG_SLUG = "acme-manufacturing"
REPORTING_YEAR = 2024


def make_csv(rows, headers):
    buf = io.BytesIO()
    text_buf = io.StringIO()
    writer = csv.DictWriter(text_buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buf.write(text_buf.getvalue().encode("utf-8"))
    buf.seek(0)
    return buf


class Command(BaseCommand):
    help = "Seed the database with demo data"

    def handle(self, *args, **options):
        # Organisation
        org, _ = Organisation.objects.get_or_create(
            slug=DEMO_ORG_SLUG,
            defaults={"name": DEMO_ORG_NAME, "active_reporting_year": REPORTING_YEAR},
        )
        self.stdout.write(f"Organisation: {org.name}")

        # Users
        admin, created = User.objects.get_or_create(
            email="admin@acme.com",
            defaults={
                "first_name": "Priya",
                "last_name": "Sharma",
                "role": User.ROLE_ADMIN,
                "organisation": org,
                "is_staff": True,
            },
        )
        if created:
            admin.set_password("demo1234")
            admin.save()
            self.stdout.write("Created admin@acme.com / demo1234")

        analyst, created = User.objects.get_or_create(
            email="analyst@acme.com",
            defaults={
                "first_name": "Rahul",
                "last_name": "Nair",
                "role": User.ROLE_ANALYST,
                "organisation": org,
            },
        )
        if created:
            analyst.set_password("demo1234")
            analyst.save()
            self.stdout.write("Created analyst@acme.com / demo1234")

        # ---- SAP Sample Data ----
        # MSEG-style flat file extract for fuel consumption
        # Plant codes: IN01 (Pune factory), IN02 (Chennai factory)
        # Movement type 201 = goods issue to cost centre (fuel consumption)
        sap_rows = []
        fuels = [
            ("Diesel (HSD)", "L", "diesel"),
            ("High Speed Diesel", "L", "diesel"),
            ("Petrol / Gasoline", "L", "petrol"),
            ("LPG - Liquid Petroleum Gas", "L", "lpg"),
            ("Natural Gas (CNG)", "M3G", "gas"),
            ("Furnace Oil", "L", "fuel_oil"),  # Will fail EF lookup — intentional
        ]
        plants = ["IN01", "IN02", "IN03"]
        cost_centres = ["CC001", "CC002", "CC003", "CC010"]

        random.seed(42)
        for i in range(35):
            fuel_desc, uom, _ = random.choice(fuels)
            plant = random.choice(plants)
            qty = round(random.uniform(50, 5000), 2)
            posting_day = date(2024, random.randint(1, 12), random.randint(1, 28))

            sap_rows.append({
                "MBLNR": f"490000{5000 + i}",
                "MJAHR": "2024",
                "ZEILE": str(i + 1).zfill(4),
                "BUDAT": posting_day.strftime("%Y%m%d"),
                "WERKS": plant,
                "MATNR": f"MAT-{1000 + i}",
                "MAKTX": fuel_desc,
                "MENGE": str(qty),
                "MEINS": uom,
                "BWART": "201",
                "KOSTL": random.choice(cost_centres),
                "LIFNR": f"VEND{random.randint(100, 200)}",
            })

        sap_csv = make_csv(sap_rows, list(sap_rows[0].keys()))
        sap_batch = IngestionBatch.objects.create(
            organisation=org,
            source_type=IngestionBatch.SOURCE_SAP,
            original_filename="sap_mseg_export_2024.csv",
            uploaded_by=admin,
        )
        run_ingestion(sap_batch, sap_csv)
        self.stdout.write(f"SAP batch: {sap_batch.rows_success} records ingested, {sap_batch.rows_failed} failed")

        # ---- Utility Sample Data ----
        # BESCOM-style portal CSV for Bangalore office + factory
        # Billing periods are irregular (not calendar months)
        utility_rows = []
        meters = [
            ("MTR-BLR-001", "Bangalore HQ", "BLR"),
            ("MTR-BLR-002", "Bangalore Factory Floor 1", "BLR"),
            ("MTR-PNQ-001", "Pune Office", "PNQ"),
        ]
        base_date = date(2024, 1, 15)
        for meter_id, facility, loc in meters:
            for month_offset in range(11):
                period_start = base_date + timedelta(days=month_offset * 31)
                period_end = period_start + timedelta(days=30)
                # Factory floor uses more; offices use less
                base_kwh = 85000 if "Factory" in facility else 12000
                kwh = round(base_kwh * random.uniform(0.85, 1.20))
                utility_rows.append({
                    "Meter Number": meter_id,
                    "Facility": facility,
                    "Start Date": period_start.strftime("%Y-%m-%d"),
                    "End Date": period_end.strftime("%Y-%m-%d"),
                    "Usage (kWh)": str(kwh),
                    "Cost": str(round(kwh * 7.5)),  # ₹7.5/kWh approx BESCOM commercial
                })

        utility_csv = make_csv(utility_rows, list(utility_rows[0].keys()))
        utility_batch = IngestionBatch.objects.create(
            organisation=org,
            source_type=IngestionBatch.SOURCE_UTILITY,
            original_filename="bescom_billing_history_2024.csv",
            uploaded_by=admin,
        )
        run_ingestion(utility_batch, utility_csv, country_code="IN")
        self.stdout.write(f"Utility batch: {utility_batch.rows_success} records ingested")

        # ---- Travel Sample Data ----
        # Navan/Concur-style export
        # Flights between Indian metros + international routes
        # Mix of economy and business class
        travel_rows = []
        travellers = [
            "ceo@acme.com", "cfo@acme.com", "vp.sales@acme.com",
            "director.ops@acme.com", "analyst@acme.com",
        ]

        # Domestic flights
        domestic_routes = [
            ("BLR", "DEL"), ("BLR", "BOM"), ("DEL", "HYD"),
            ("BOM", "CCU"), ("MAA", "DEL"), ("BLR", "MAA"),
        ]
        # International
        intl_routes = [
            ("BLR", "LHR"), ("DEL", "JFK"), ("BOM", "DXB"),
            ("BLR", "SIN"), ("DEL", "CDG"), ("BOM", "FRA"),
        ]

        for i in range(25):
            is_intl = random.random() > 0.6
            route = random.choice(intl_routes if is_intl else domestic_routes)
            cabin = "Business" if (is_intl and random.random() > 0.5) else "Economy"
            travel_date = date(2024, random.randint(1, 12), random.randint(1, 28))

            travel_rows.append({
                "travel_type": "flight",
                "traveler_email": random.choice(travellers),
                "travel_date": travel_date.strftime("%Y-%m-%d"),
                "origin_iata": route[0],
                "destination_iata": route[1],
                "cabin_class": cabin,
                "distance_km": "",  # intentionally blank for some — parser will calculate
                "hotel_nights": "",
                "hotel_city": "",
            })

        # Hotels
        cities = ["London", "New York", "Dubai", "Singapore", "Paris", "Frankfurt"]
        for i in range(12):
            nights = random.randint(1, 5)
            travel_date = date(2024, random.randint(1, 12), random.randint(1, 28))
            travel_rows.append({
                "travel_type": "hotel",
                "traveler_email": random.choice(travellers),
                "travel_date": travel_date.strftime("%Y-%m-%d"),
                "origin_iata": "",
                "destination_iata": "",
                "cabin_class": "",
                "distance_km": "",
                "hotel_nights": str(nights),
                "hotel_city": random.choice(cities),
            })

        # Ground transport
        for i in range(8):
            travel_date = date(2024, random.randint(1, 12), random.randint(1, 28))
            travel_rows.append({
                "travel_type": random.choice(["taxi", "car rental"]),
                "traveler_email": random.choice(travellers),
                "travel_date": travel_date.strftime("%Y-%m-%d"),
                "origin_iata": "",
                "destination_iata": "",
                "cabin_class": "",
                "distance_km": str(round(random.uniform(15, 120), 1)),
                "hotel_nights": "",
                "hotel_city": "",
            })

        travel_csv = make_csv(travel_rows, list(travel_rows[0].keys()))
        travel_batch = IngestionBatch.objects.create(
            organisation=org,
            source_type=IngestionBatch.SOURCE_TRAVEL,
            original_filename="navan_travel_export_2024.csv",
            uploaded_by=admin,
        )
        run_ingestion(travel_batch, travel_csv)
        self.stdout.write(f"Travel batch: {travel_batch.rows_success} records ingested, {travel_batch.rows_failed} failed")

        self.stdout.write(self.style.SUCCESS("\n✓ Demo seed complete."))
        self.stdout.write("  Login: admin@acme.com / demo1234")
        self.stdout.write("  Login: analyst@acme.com / demo1234")
