from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "journal d'audit"

    def ready(self):
        from audit import signaux  # noqa: F401
