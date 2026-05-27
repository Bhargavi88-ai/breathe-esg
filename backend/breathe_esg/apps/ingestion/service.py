"""
Ingestion service — ties parsers to database writes.

Handles:
  - Deduplication via source_row_hash
  - Atomic batch processing (all-or-nothing per batch)
  - Error recording
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from breathe_esg.apps.emissions.models import EmissionRecord
from breathe_esg.apps.ingestion.models import IngestionBatch, IngestionError
from breathe_esg.apps.ingestion.parsers.sap_parser import process_sap_batch
from breathe_esg.apps.ingestion.parsers.utility_parser import process_utility_batch
from breathe_esg.apps.ingestion.parsers.travel_parser import process_travel_batch


def run_ingestion(batch: IngestionBatch, file_obj, country_code: str = "IN") -> IngestionBatch:
    """
    Process an ingestion batch. Updates batch counters and creates EmissionRecords.
    Returns the updated batch.
    """
    batch.status = IngestionBatch.STATUS_PROCESSING
    batch.save(update_fields=["status"])

    ef = settings.EMISSION_FACTORS
    organisation = batch.organisation
    reporting_year = organisation.active_reporting_year

    try:
        if batch.source_type == IngestionBatch.SOURCE_SAP:
            successes, errors = process_sap_batch(
                file_obj, batch, organisation, reporting_year, ef
            )
        elif batch.source_type == IngestionBatch.SOURCE_UTILITY:
            successes, errors = process_utility_batch(
                file_obj, batch, organisation, reporting_year, ef, country_code=country_code
            )
        elif batch.source_type == IngestionBatch.SOURCE_TRAVEL:
            successes, errors = process_travel_batch(
                file_obj, batch, organisation, reporting_year, ef
            )
        else:
            raise ValueError(f"Unknown source type: {batch.source_type}")

    except Exception as e:
        batch.status = IngestionBatch.STATUS_FAILED
        batch.error_message = str(e)
        batch.completed_at = timezone.now()
        batch.save(update_fields=["status", "error_message", "completed_at"])
        return batch

    # Write to DB inside a transaction
    with transaction.atomic():
        # Write errors
        for err in errors:
            IngestionError.objects.create(
                batch=batch,
                row_index=err.get("row_index"),
                raw_data=err.get("raw_data", ""),
                error_message=err.get("error_message", ""),
            )

        # Write successes — deduplicate on source_row_hash
        existing_hashes = set(
            EmissionRecord.objects.filter(organisation=organisation)
            .values_list("source_row_hash", flat=True)
        )

        duplicates = 0
        created = 0
        to_create = []

        for rec in successes:
            row_hash = rec.get("source_row_hash", "")
            if row_hash and row_hash in existing_hashes:
                duplicates += 1
                continue
            if row_hash:
                existing_hashes.add(row_hash)

            to_create.append(
                EmissionRecord(
                    organisation=organisation,
                    ingestion_batch=batch,
                    **{k: v for k, v in rec.items()},
                )
            )

        EmissionRecord.objects.bulk_create(to_create, batch_size=500)
        created = len(to_create)

        batch.rows_total = len(successes) + len(errors)
        batch.rows_success = created
        batch.rows_failed = len(errors)
        batch.rows_duplicate = duplicates
        batch.status = IngestionBatch.STATUS_DONE
        batch.completed_at = timezone.now()
        batch.save()

    return batch
