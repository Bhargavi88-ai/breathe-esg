"""
Emissions models — the canonical normalized record.

Design principles:
- Every emission record is source-of-truth tracked: which ingestion batch created it,
  which file, which row, when, and whether it was edited after the fact.
- Scope 1/2/3 categorisation is a first-class field, not an afterthought.
- Units are normalised at write time; raw values are kept for audit.
- Analyst review state machine: pending → approved | flagged → approved
- Once approved and locked, no further edits are possible (audit lock).
"""
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class EmissionRecord(models.Model):
    """
    One normalised emission event.

    Raw data comes in from three sources:
      - SAP flat-file export (fuel & procurement, Scope 1)
      - Utility portal CSV (electricity, Scope 2)
      - Concur/Navan JSON/CSV export (travel, Scope 3)

    After ingestion, the parser normalises units to:
      - quantity_kwh for energy
      - quantity_litres for liquid fuel
      - quantity_km for distance
      - quantity_nights for hotel stays

    The carbon field (kg_co2e) is computed from the normalised quantity
    multiplied by an emission factor at ingestion time. The factor used
    is stored so the calculation is reproducible.
    """

    # --- Scope categorisation ---
    SCOPE_1 = "1"
    SCOPE_2 = "2"
    SCOPE_3 = "3"
    SCOPE_CHOICES = [
        (SCOPE_1, "Scope 1 – Direct"),
        (SCOPE_2, "Scope 2 – Electricity"),
        (SCOPE_3, "Scope 3 – Value chain"),
    ]

    # --- Source types ---
    SOURCE_SAP = "sap"
    SOURCE_UTILITY = "utility"
    SOURCE_TRAVEL = "travel"
    SOURCE_CHOICES = [
        (SOURCE_SAP, "SAP Export"),
        (SOURCE_UTILITY, "Utility Portal"),
        (SOURCE_TRAVEL, "Corporate Travel"),
    ]

    # --- Review state machine ---
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_FLAGGED = "flagged"
    STATUS_LOCKED = "locked"   # approved + locked for audit; immutable
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_FLAGGED, "Flagged"),
        (STATUS_LOCKED, "Locked for Audit"),
    ]

    # --- Activity sub-categories ---
    CATEGORY_FUEL = "fuel"
    CATEGORY_PROCUREMENT = "procurement"
    CATEGORY_ELECTRICITY = "electricity"
    CATEGORY_FLIGHT = "flight"
    CATEGORY_HOTEL = "hotel"
    CATEGORY_GROUND = "ground_transport"
    CATEGORY_CHOICES = [
        (CATEGORY_FUEL, "Fuel"),
        (CATEGORY_PROCUREMENT, "Procurement"),
        (CATEGORY_ELECTRICITY, "Electricity"),
        (CATEGORY_FLIGHT, "Flight"),
        (CATEGORY_HOTEL, "Hotel Stay"),
        (CATEGORY_GROUND, "Ground Transport"),
    ]

    # --- Identity ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        related_name="emission_records",
    )

    # --- Source provenance ---
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    ingestion_batch = models.ForeignKey(
        "ingestion.IngestionBatch",
        on_delete=models.PROTECT,
        related_name="emission_records",
        null=True,
        blank=True,
    )
    # The raw source row index, so we can trace back to the original file
    source_row_index = models.IntegerField(null=True, blank=True)
    # Hash of the raw row content — detects duplicate ingestion
    source_row_hash = models.CharField(max_length=64, blank=True, db_index=True)

    # --- Categorisation ---
    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    sub_category = models.CharField(max_length=100, blank=True)  # e.g. flight class, fuel type

    # --- Activity data (raw, as it came in) ---
    raw_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    raw_unit = models.CharField(max_length=50, blank=True)  # e.g. "GAL", "MMBTU", "kWh"
    raw_description = models.TextField(blank=True)

    # --- Normalised activity data ---
    # We store the primary normalised dimension for the category.
    # For fuel: litres; for electricity: kWh; for distance: km; for hotel: nights.
    normalised_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True)
    normalised_unit = models.CharField(max_length=20, blank=True)  # always SI or agreed unit

    # --- Carbon calculation ---
    emission_factor_key = models.CharField(max_length=100, blank=True)  # e.g. "diesel_litre"
    emission_factor_value = models.DecimalField(max_digits=12, decimal_places=6, null=True)
    kg_co2e = models.DecimalField(max_digits=18, decimal_places=4, null=True)

    # --- Time & location ---
    activity_date = models.DateField(null=True, blank=True)
    activity_period_start = models.DateField(null=True, blank=True)
    activity_period_end = models.DateField(null=True, blank=True)
    reporting_year = models.IntegerField()
    facility_code = models.CharField(max_length=100, blank=True)  # SAP plant code etc.
    facility_name = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=3, blank=True)  # ISO 3166-1 alpha-2

    # --- Extra metadata (source-specific fields) ---
    # Stored as JSON so we don't need schema changes per source.
    extra = models.JSONField(default=dict, blank=True)

    # --- Review workflow ---
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_records",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # --- Audit trail ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Track if a human edited the record after ingestion
    manually_edited = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "emission_records"
        indexes = [
            models.Index(fields=["organisation", "reporting_year", "status"]),
            models.Index(fields=["organisation", "scope", "reporting_year"]),
            models.Index(fields=["source_type", "ingestion_batch"]),
        ]
        ordering = ["-activity_date", "-created_at"]

    def __str__(self):
        return f"{self.organisation} | {self.scope} | {self.category} | {self.activity_date} | {self.kg_co2e} kgCO2e"

    def approve(self, user):
        """Analyst approves this record."""
        if self.status == self.STATUS_LOCKED:
            raise ValueError("Record is locked for audit.")
        self.status = self.STATUS_APPROVED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    def flag(self, user, note=""):
        """Analyst flags this record for follow-up."""
        if self.status == self.STATUS_LOCKED:
            raise ValueError("Record is locked for audit.")
        self.status = self.STATUS_FLAGGED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

    def lock(self):
        """Lock for audit. Irreversible."""
        self.status = self.STATUS_LOCKED
        self.locked_at = timezone.now()
        self.save(update_fields=["status", "locked_at", "updated_at"])
