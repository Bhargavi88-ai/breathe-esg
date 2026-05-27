from django.urls import path
from .serializers import AuditEventListView

urlpatterns = [
    path("events/", AuditEventListView.as_view(), name="audit-events"),
]
