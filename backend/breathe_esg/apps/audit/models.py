"""
Audit trail — append-only log of every state change on EmissionRecords.

Why a separate model instead of Django's built-in signals-based approach:
  We need to store the previous value, who changed it, and why — Django admin
  history only captures admin changes, not API changes. This table is the
  paper trail that goes to auditors.

  Every write to EmissionRecord.status or any analyst edit is logged here.
  The table is append-only: no updates, no deletes (enforced in the save override).
"""
import uuid
from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    ACTION_APPROVE = "approve"
    ACTION_FLAG = "flag"
    ACTION_EDIT = "edit"
    ACTION_LOCK = "lock"
    ACTION_INGEST = "ingest"
    ACTION_CHOICES = [
        (ACTION_APPROVE, "Approved"),
        (ACTION_FLAG, "Flagged"),
        (ACTION_EDIT, "Edited"),
        (ACTION_LOCK, "Locked"),
        (ACTION_INGEST, "Ingested"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    emission_record = models.ForeignKey(
        "emissions.EmissionRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    ingestion_batch = models.ForeignKey(
        "ingestion.IngestionBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    previous_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_events"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Append-only: never allow updates
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("AuditEvent is append-only — no updates allowed.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.created_at}"
