from rest_framework import serializers
from .models import EmissionRecord


class EmissionRecordSerializer(serializers.ModelSerializer):
    reviewed_by_email = serializers.SerializerMethodField()
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)

    class Meta:
        model = EmissionRecord
        fields = [
            "id",
            "organisation",
            "source_type",
            "source_type_display",
            "ingestion_batch",
            "source_row_index",
            "scope",
            "scope_display",
            "category",
            "category_display",
            "sub_category",
            "raw_quantity",
            "raw_unit",
            "raw_description",
            "normalised_quantity",
            "normalised_unit",
            "emission_factor_key",
            "emission_factor_value",
            "kg_co2e",
            "activity_date",
            "activity_period_start",
            "activity_period_end",
            "reporting_year",
            "facility_code",
            "facility_name",
            "country_code",
            "extra",
            "status",
            "status_display",
            "review_note",
            "reviewed_by",
            "reviewed_by_email",
            "reviewed_at",
            "created_at",
            "updated_at",
            "manually_edited",
            "locked_at",
        ]
        read_only_fields = [
            "id",
            "organisation",
            "source_type",
            "ingestion_batch",
            "source_row_index",
            "source_row_hash",
            "scope",
            "category",
            "emission_factor_key",
            "emission_factor_value",
            "kg_co2e",
            "created_at",
            "updated_at",
            "locked_at",
        ]

    def get_reviewed_by_email(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.email
        return None


class EmissionRecordUpdateSerializer(serializers.ModelSerializer):
    """Only fields an analyst is allowed to touch."""
    class Meta:
        model = EmissionRecord
        fields = ["review_note", "raw_description", "facility_name", "country_code"]

    def save(self, **kwargs):
        instance = super().save(**kwargs)
        # Mark as manually edited whenever a human touches it
        instance.manually_edited = True
        instance.save(update_fields=["manually_edited"])
        return instance


class SummarySerializer(serializers.Serializer):
    scope = serializers.CharField()
    scope_display = serializers.CharField()
    total_kg_co2e = serializers.DecimalField(max_digits=18, decimal_places=2)
    record_count = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    approved_count = serializers.IntegerField()
    flagged_count = serializers.IntegerField()
