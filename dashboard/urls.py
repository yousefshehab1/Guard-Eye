from django.urls import path
from . import views
from . import analytics_views

app_name = "dashboard"

urlpatterns = [
    # Main views
    path("signup/", views.user_signup, name="signup"),
    path("", views.dashboard, name="dashboard"),
    path("alerts/", views.alerts_view, name="alerts"),
    path("reports/", views.reports_view, name="reports"),
    path("create-alert/", views.create_alert, name="create_alert"),
    path('camera/toggle/<int:camera_id>/', views.toggle_camera, name='toggle_camera'),

    # Camera monitoring
    path("start-monitoring/<int:camera_id>/", views.start_camera_monitoring, name="start_monitoring"),
    path("stop-monitoring/<int:camera_id>/", views.stop_camera_monitoring, name="stop_monitoring"),
    path("video-feed/", views.video_feed, name="video_feed"),
    
    # Analytics
    path("analytics/", analytics_views.analytics_dashboard, name="analytics"),
    path("analytics-data/", analytics_views.analytics_data, name="analytics_data"),
    
    # Alert management
    path("mark-alert-read/<int:alert_id>/", views.mark_alert_read, name="mark_alert_read"),
    path("delete-alert/<int:alert_id>/", views.delete_alert, name="delete_alert"),
    
    # API endpoints
    path("api/alerts/", views.api_alerts, name="api_alerts"),
    path("api/camera-status/", views.api_camera_status, name="api_camera_status"),
    
    # Settings
    path("notification-settings/", views.notification_settings_view, name="notification_settings"),
    path("update-notification-settings/", views.update_notification_settings, name="update_notification_settings"),
    path("force-camera-scan/", views.force_camera_scan, name="force_camera_scan"),
    path('chatbot/send_message/', views.send_message, name='send_message'),
    path("chatbot/", views.chatbot_view, name="chatbot"),

    # مسارات نظام المراقبة
    path('monitoring/start/', views.start_monitoring, name='start_monitoring'),
    path('monitoring/stop/', views.stop_monitoring, name='stop_monitoring'),
    path('monitoring/status/', views.get_monitoring_status, name='get_monitoring_status'),
    path('monitoring/settings/', views.update_notification_settings, name='update_notification_settings'),

    path('video-feed/', views.video_feed, name='video_feed'),
]
