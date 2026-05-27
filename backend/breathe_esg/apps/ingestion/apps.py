from django.apps import AppConfig


class IngestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "breathe_esg.apps.ingestion"
    label = "ingestion"
