from django.urls import path
from . import views

urlpatterns = [
    path("upload/", views.upload_file, name="ingestion-upload"),
    path("batches/", views.IngestionBatchListView.as_view(), name="ingestion-batch-list"),
    path("batches/<uuid:pk>/", views.IngestionBatchDetailView.as_view(), name="ingestion-batch-detail"),
]
