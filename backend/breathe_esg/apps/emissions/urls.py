from django.urls import path
from . import views

urlpatterns = [
    path("records/", views.EmissionRecordListView.as_view(), name="emission-list"),
    path("records/<uuid:pk>/", views.EmissionRecordDetailView.as_view(), name="emission-detail"),
    path("records/<uuid:pk>/approve/", views.approve_record, name="emission-approve"),
    path("records/<uuid:pk>/flag/", views.flag_record, name="emission-flag"),
    path("records/bulk-approve/", views.bulk_approve, name="emission-bulk-approve"),
    path("summary/", views.summary, name="emission-summary"),
]
