from rest_framework import serializers
from .models import IngestionBatch, IngestionError


class IngestionErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionError
        fields = ["id", "row_index", "raw_data", "error_message", "created_at"]


class IngestionBatchSerializer(serializers.ModelSerializer):
    errors = IngestionErrorSerializer(many=True, read_only=True)
    uploaded_by_email = serializers.SerializerMethodField()
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            "id",
            "source_type",
            "source_type_display",
            "status",
            "status_display",
            "original_filename",
            "rows_total",
            "rows_success",
            "rows_failed",
            "rows_duplicate",
            "uploaded_by_email",
            "error_message",
            "created_at",
            "completed_at",
            "errors",
        ]
        read_only_fields = fields

    def get_uploaded_by_email(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.email
        return None


class IngestionUploadSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=IngestionBatch.SOURCE_CHOICES)
    file = serializers.FileField()
    country_code = serializers.CharField(max_length=3, default="IN", required=False)
