from django.apps import AppConfig


class BidsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bids'

    def ready(self):
        # Import signals here so they’re registered
        import bids.signals