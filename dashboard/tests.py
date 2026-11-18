from django.contrib.auth.models import User
from .models import Camera, Alert, NotificationSettings
from .utils import send_notification


def test_notification():
    # Create a test user
    user = User.objects.create_user(
        username="testuser", email="testuser@example.com", password="testpass"
    )

    # Create a test camera
    camera = Camera.objects.create(
        camera_id="test_camera", name="Test Camera", user=user
    )

    # Create a test alert
    alert = Alert.objects.create(
        camera=camera, description="Test alert", severity="Medium"
    )

    # Create notification settings
    NotificationSettings.objects.create(
        user=user,
        email_notifications=True,
        telegram_notifications=True,
        whatsapp_notifications=True,
        telegram_chat_id="123456789",
        whatsapp_number="+1234567890",
    )

    # Send test notification
    send_notification(alert)


# Run the test
if __name__ == "__main__":
    test_notification()
