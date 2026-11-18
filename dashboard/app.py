from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"

    def ready(self):
        # Start the security monitor when the app is ready
        try:
            import os

            if os.environ.get("RUN_MAIN") == "true":  # Only run in main process
                from .views import get_security_monitor

                monitor = get_security_monitor()
                monitor.start_monitoring()
        except Exception as e:
            print(f"Error starting security monitor: {e}")
