"""
Ingestion models.

IngestionBatch: one upload / one API pull = one batch.
Every EmissionRecord points back to the batch that created it.
IngestionError: rows that failed to parse (shown to analyst).

Design choice: we store the original file on disk so analysts can
download it and cross-check. We never delete it after ingestion.
"""
import uuid
from django.conf import settings
from django.db import models


class IngestionBatch(models.Model):
    SOURCE_SAP = "sap"
    SOURCE_UTILITY = "utility"
    SOURCE_TRAVEL = "travel"
    SOURCE_CHOICES = [
        (SOURCE_SAP, "SAP Export"),
        (SOURCE_UTILITY, "Utility Portal CSV"),
        (SOURCE_TRAVEL, "Corporate Travel"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        related_name="ingestion_batches",
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # The uploaded file (kept permanently for audit)
    uploaded_file = models.FileField(upload_to="ingestion/%Y/%m/", null=True, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)

    # Counts set after processing
    rows_total = models.IntegerField(default=0)
    rows_success = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    rows_duplicate = models.IntegerField(default=0)

    # Who triggered this
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="ingestion_batches",
    )
    error_message = models.TextField(blank=True)  # top-level failure reason if status=failed

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ingestion_batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source_type} | {self.original_filename} | {self.status}"


class IngestionError(models.Model):
    """Row-level parse failures surfaced to the analyst dashboard."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="errors")
    row_index = models.IntegerField(null=True, blank=True)
    raw_data = models.TextField(blank=True)  # repr of the failing row
    error_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ingestion_errors"
        ordering = ["row_index"]
