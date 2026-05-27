"""
Main URL configuration for Breathe ESG.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("breathe_esg.apps.accounts.urls")),
    path("api/v1/ingestion/", include("breathe_esg.apps.ingestion.urls")),
    path("api/v1/emissions/", include("breathe_esg.apps.emissions.urls")),
    path("api/v1/audit/", include("breathe_esg.apps.audit.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
