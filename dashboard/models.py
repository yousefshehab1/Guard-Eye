from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Camera(models.Model):
    users = models.ManyToManyField(User)
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, null=True, blank=True)
    camera_url = models.URLField(blank=True, null=True)
    camera_index = models.IntegerField(default=0)  # للكاميرات المحلية
    is_active = models.BooleanField(default=True)
    is_monitoring = models.BooleanField(default=False)  # حالة المراقبة
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.location}"

    class Meta:
        ordering = ["-created_at"]


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ("low", "منخفض"),
        ("medium", "متوسط"),
        ("high", "عالي"),
    ]

    CATEGORY_CHOICES = [
        ("violence", "عنف"),
        ("thief_mask", "لص مقنع"),
        ("fire", "حريق"),
        ("weapon", "سلاح"),
        ("thief", "لص"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, null=True, blank=True)
    description = models.TextField()
    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default="medium"
    )
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="violence"
    )
    confidence = models.FloatField(default=0.0)  # نسبة الثقة
    timestamp = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)
    image = models.ImageField(upload_to="alerts/", null=True, blank=True)

    def __str__(self):
        return f"{self.description[:50]} - {self.timestamp}"

    class Meta:
        ordering = ["-timestamp"]


class NotificationSettings(models.Model):
    """إعدادات الإشعارات للمستخدم"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_notifications = models.BooleanField(default=False)
    telegram_username = models.CharField(max_length=255, blank=True, null=True)
    telegram_chat_id = models.CharField(max_length=255, blank=True, null=True)
    whatsapp_notifications = models.BooleanField(default=False)
    whatsapp_number = models.CharField(max_length=255, blank=True, null=True)
    email_notifications = models.BooleanField(default=False)
    notification_interval = models.IntegerField(default=5, help_text="Interval in minutes between notifications")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Notification Settings for {self.user.username}"

    class Meta:
        verbose_name = "Notification Setting"
        verbose_name_plural = "Notification Settings"


class SecurityIncident(models.Model):
    incident_type = models.CharField(max_length=100)
    description = models.TextField()
    location = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    severity = models.CharField(max_length=50)
    response_taken = models.TextField()

    class Meta:
        db_table = 'security_incidents'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.incident_type} at {self.location} - {self.timestamp}"
