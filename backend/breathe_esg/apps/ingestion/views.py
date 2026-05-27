import io
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import IngestionBatch
from .serializers import IngestionBatchSerializer, IngestionUploadSerializer
from .service import run_ingestion


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_file(request):
    """
    Upload a file for ingestion.
    Multipart form: source_type, file, country_code (optional).
    Processing is synchronous for simplicity (in prod: Celery task).
    """
    serializer = IngestionUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    source_type = serializer.validated_data["source_type"]
    uploaded_file = serializer.validated_data["file"]
    country_code = serializer.validated_data.get("country_code", "IN")

    batch = IngestionBatch.objects.create(
        organisation=request.user.organisation,
        source_type=source_type,
        uploaded_file=uploaded_file,
        original_filename=uploaded_file.name,
        uploaded_by=request.user,
    )

    # Re-open the stored file for parsing
    batch.uploaded_file.seek(0)
    file_bytes = batch.uploaded_file.read()
    file_obj = io.BytesIO(file_bytes)

    batch = run_ingestion(batch, file_obj, country_code=country_code)

    return Response(
        IngestionBatchSerializer(batch).data,
        status=status.HTTP_201_CREATED if batch.status == IngestionBatch.STATUS_DONE else status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


class IngestionBatchListView(generics.ListAPIView):
    serializer_class = IngestionBatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return IngestionBatch.objects.filter(
            organisation=self.request.user.organisation
        ).prefetch_related("errors")


class IngestionBatchDetailView(generics.RetrieveAPIView):
    serializer_class = IngestionBatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return IngestionBatch.objects.filter(
            organisation=self.request.user.organisation
        ).prefetch_related("errors")
