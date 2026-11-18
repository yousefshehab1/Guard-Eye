from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.http import (
    JsonResponse,
    StreamingHttpResponse,
    HttpResponse,
    HttpResponseNotFound,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.contrib.auth.models import User
from asgiref.sync import sync_to_async, async_to_sync
from .models import Camera, Alert, NotificationSettings
from .live_security_monitor import LiveSecurityMonitor
from .forms import UserRegistrationForm, NotificationSettingsForm
import json
import threading
import time
from datetime import datetime, timedelta
import logging
import cv2
import asyncio
from channels.layers import get_channel_layer
from django.views.decorators import gzip
import numpy as np
from .rag_system import SurveillanceRAGSystem
from .notifications import get_security_notifier
from .utils import get_camera_instance

logger = logging.getLogger(__name__)

# Global variable to store active monitor instances
active_monitors = {}

# Initialize RAG system
rag_system = SurveillanceRAGSystem()

# إزالة الدالة القديمة لأنها لم تعد مستخدمة
def get_security_monitor():
    pass


def user_signup(request):
    """User signup view"""
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = User.objects.create_user(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                )
                NotificationSettings.objects.create(
                    user=user,
                    email_notifications=True,
                    telegram_notifications=False,
                    whatsapp_notifications=False,
                )
                logger.info(f"تم إنشاء حساب جديد للمستخدم {user.username}")
                messages.success(
                    request, "تم إنشاء الحساب بنجاح. يمكنك الآن تسجيل الدخول."
                )
                return redirect("login")
            except Exception as e:
                logger.error(f"خطأ في إنشاء الحساب: {str(e)}")
                messages.error(request, f"حدث خطأ في إنشاء الحساب: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    else:
        form = UserRegistrationForm()
    return render(request, "registration/login.html", {"form": form})


@login_required
def dashboard(request):
    """Main dashboard view"""
    try:
        try:
            recent_alerts = Alert.objects.filter(user=request.user).order_by(
                "-timestamp"
            )[:5]
        except Exception:
            recent_alerts = []
        try:
            cameras = Camera.objects.filter(users=request.user)
            total_cameras = cameras.count()
            active_cameras = cameras.filter(is_active=True).count()
            for camera in cameras.filter(is_active=True):
                if camera.id not in active_monitors:
                    start_camera_monitoring(request, camera.id)
        except Exception as e:
            logger.error(f"Error getting cameras in dashboard view: {e}")
            cameras = []
            total_cameras = 0
            active_cameras = 0
        context = {
            "recent_alerts": recent_alerts,
            "cameras": cameras,
            "total_cameras": total_cameras,
            "active_cameras": active_cameras,
        }
        return render(request, "dashboard/dashboard.html", context)
    except Exception as e:
        logger.error(f"Error in dashboard view: {e}")
        messages.error(request, "حدث خطأ في تحميل لوحة التحكم")
        return render(
            request,
            "dashboard/dashboard.html",
            {
                "cameras": [],
                "recent_alerts": [],
                "total_cameras": 0,
                "active_cameras": 0,
            },
        )


@login_required
def alerts_view(request):
    """Alerts page view"""
    try:
        # The alerts are now fetched by JavaScript using api_alerts
        # This view primarily serves the HTML template
        return render(request, "dashboard/alerts.html")
    except Exception as e:
        logger.error(f"Error in alerts view: {e}")
        return render(request, "dashboard/alerts.html")


@login_required
def create_alert(request):
    # Placeholder for creating a new alert
    return render(request, "dashboard/create_alert.html")


@login_required
def cameras_view(request):
    """Cameras management view - اكتشاف الكاميرات تلقائيًا"""
    cameras = Camera.objects.filter(users=request.user)
    return render(request, "dashboard/cameras.html", {"cameras": cameras})


@login_required
def reports_view(request):
    """Reports view"""
    try:
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        if not start_date:
            start_date = (timezone.now() - timedelta(days=30)).date()
        if not end_date:
            end_date = timezone.now().date()
        alerts = Alert.objects.filter(
            user=request.user, timestamp__date__range=[start_date, end_date]
        )
        total_alerts = alerts.count()
        high_severity = alerts.filter(severity="high").count()
        medium_severity = alerts.filter(severity="medium").count()
        low_severity = alerts.filter(severity="low").count()
        context = {
            "total_alerts": total_alerts,
            "high_severity": high_severity,
            "medium_severity": medium_severity,
            "low_severity": low_severity,
            "start_date": start_date,
            "end_date": end_date,
        }
    except Exception as e:
        logger.error(f"Error in reports view: {e}")
        context = {
            "total_alerts": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "start_date": timezone.now().date(),
            "end_date": timezone.now().date(),
        }
    return render(request, "dashboard/reports.html", context)


@login_required
def notification_settings_view(request):
    """Notification settings view"""
    settings, created = NotificationSettings.objects.get_or_create(
        user=request.user,
        defaults={
            "email_notifications": False,
            "telegram_notifications": False,
            "whatsapp_notifications": False,
            "notification_interval": 60,
            "is_active": True
        }
    )
    
    if request.method == "POST":
        form = NotificationSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, "تم حفظ إعدادات الإشعارات بنجاح")
            return redirect("dashboard:notification_settings")
    else:
        form = NotificationSettingsForm(instance=settings)
    
    return render(
        request,
        "dashboard/notification_settings.html",
        {"settings": settings, "form": form}
    )


@login_required
def analytics_dashboard(request):
    """Analytics dashboard view"""
    alerts_by_day = (
        Alert.objects.filter(
            user=request.user, timestamp__gte=timezone.now() - timedelta(days=30)
        )
        .extra(select={"day": "date(timestamp)"})
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    alerts_by_severity = (
        Alert.objects.filter(user=request.user)
        .values("severity")
        .annotate(count=Count("id"))
    )
    context = {
        "alerts_by_day": list(alerts_by_day),
        "alerts_by_severity": list(alerts_by_severity),
    }
    return render(request, "dashboard/analytics.html", context)


@login_required
def analytics_data(request):
    """API endpoint for analytics data"""
    try:
        # الحصول على الفلاتر من الطلب
        date_range = request.GET.get('date', '') # Use 'date' instead of 'date_range' as per alerts_page.js
        threat_type = request.GET.get('threat_type', 'all')
        severity = request.GET.get('severity', 'all')

        # تحليل الفترة الزمنية
        start_date, end_date = (timezone.now() - timedelta(days=30)).date(), timezone.now().date() # Default if no filter
        if date_range == 'today':
            start_date = timezone.now().date()
            end_date = timezone.now().date()
        elif date_range == 'week':
            start_date = timezone.now().date() - timedelta(days=timezone.now().date().weekday())
            end_date = timezone.now().date()
        elif date_range == 'month':
            start_date = timezone.now().date().replace(day=1)
            end_date = timezone.now().date()

        alerts_qs = Alert.objects.filter(timestamp__date__range=[start_date, end_date], user=request.user)

        if threat_type != 'all':
            alerts_qs = alerts_qs.filter(category__iexact=threat_type)
        if severity != 'all':
            alerts_qs = alerts_qs.filter(severity__iexact=severity)

        # Prepare alerts data for JSON response for alerts_page.js
        alerts_data = []
        for alert in alerts_qs:
            alerts_data.append({
                "id": alert.id,
                "detection_type": alert.detection_type,
                "message": alert.message,
                "timestamp": alert.timestamp.strftime("%Y-%m-%d %H:%M"),
                "severity": alert.severity,
                "location": alert.location,
                "confidence": f"{alert.confidence:.2f}",
                "is_read": alert.is_read,
                "camera_name": alert.camera.name if alert.camera else "Unknown", # Assuming camera object is accessible
            })

        return JsonResponse({"alerts": alerts_data}, status=200)
    except Exception as e:
        logger.error(f"Error in analytics_data: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def add_camera(request):
    """Add new camera"""
    if request.method == "POST":
        name = request.POST.get("name")
        location = request.POST.get("location")
        camera_url = request.POST.get("camera_url", "")
        camera_index = int(request.POST.get("camera_index", 0))
        camera = Camera.objects.create(
            name=name,
            location=location,
            camera_url=camera_url,
            camera_index=camera_index,
            is_active=True,
        )
        camera.users.add(request.user)
        messages.success(request, f"تم إضافة الكاميرا {name} بنجاح")
        return redirect("dashboard:cameras")
    return render(request, "dashboard/add_camera.html")


@login_required
def delete_camera(request, camera_id):
    """Delete camera"""
    camera = get_object_or_404(Camera, id=camera_id, users=request.user)
    camera_name = camera.name
    stop_camera_monitoring(request, camera_id)
    camera.users.remove(request.user)
    if camera.users.count() == 0:
        camera.delete()
    messages.success(request, f"تم حذف الكاميرا {camera_name} بنجاح")
    return redirect("dashboard:cameras")


@login_required
@require_http_methods(["POST"])
def toggle_camera(request, camera_id):
    """Toggle camera active status"""
    try:
        camera = get_object_or_404(Camera, id=camera_id, users=request.user)
        camera.is_active = not camera.is_active
        camera.save()
        if camera.is_active:
            start_camera_monitoring(request, camera_id)
        else:
            stop_camera_monitoring(request, camera_id)
        return JsonResponse(
            {"status": camera.is_active, "message": "تم تحديث حالة الكاميرا بنجاح"}
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def open_camera_with_logging():
    camera_index = 0
    logging.warning(f"Trying to open camera with index: {camera_index}")
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    if not cap.isOpened():
        logging.error(f"❌ فشل في فتح الكاميرا رقم {camera_index}")
    else:
        logging.info(f"✅ تم فتح الكاميرا رقم {camera_index} بنجاح")
    return cap


def list_available_cameras():
    """List all available cameras in the system"""
    available_cameras = []
    # فقط نحاول الكاميرا 0
    cap = open_camera_with_logging()
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            available_cameras.append(0)
            logger.info(f"Camera 0 is available")
        cap.release()
    return available_cameras


@login_required
def start_camera_monitoring(request, camera_id):
    """بدء مراقبة الكاميرا"""
    try:
        # التحقق من وجود الكاميرا
        try:
            camera = Camera.objects.get(id=camera_id)
        except Camera.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "الكاميرا غير موجودة"}, status=404
            )

        # التحقق من حالة المراقب
        if camera_id in active_monitors and active_monitors[camera_id].is_running:
            return JsonResponse(
                {"status": "error", "message": "الكاميرا قيد المراقبة بالفعل"},
                status=400,
            )

        # إنشاء مراقب جديد
        monitor = LiveSecurityMonitor(camera_id)
        if monitor.start_monitoring():
            active_monitors[camera_id] = monitor
            logger.info(f"Started monitoring camera {camera_id}")
            return JsonResponse(
                {"status": "success", "message": "تم بدء مراقبة الكاميرا بنجاح"}
            )
        else:
            return JsonResponse(
                {"status": "error", "message": "فشل في بدء مراقبة الكاميرا"}, status=500
            )

    except Exception as e:
        logger.error(f"Error starting camera monitoring: {str(e)}")
        return JsonResponse(
            {"status": "error", "message": "حدث خطأ أثناء بدء مراقبة الكاميرا"},
            status=500,
        )


@login_required
def stop_camera_monitoring(request, camera_id):
    """إيقاف مراقبة الكاميرا"""
    try:
        # التحقق من وجود الكاميرا
        try:
            camera = Camera.objects.get(id=camera_id)
        except Camera.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "الكاميرا غير موجودة"}, status=404
            )

        # التحقق من حالة المراقب
        monitor = active_monitors.get(camera_id)
        if not monitor:
            return JsonResponse(
                {"status": "error", "message": "المراقب غير نشط"}, status=400
            )

        # إيقاف المراقب
        try:
            if hasattr(monitor, "stop_monitoring"):
                monitor.stop_monitoring()
            else:
                monitor.is_running = False
                if monitor.camera is not None:
                    monitor.camera.release()
            del active_monitors[camera_id]
            logger.info(f"Stopped monitoring camera {camera_id}")
            return JsonResponse(
                {"status": "success", "message": "تم إيقاف مراقبة الكاميرا بنجاح"}
            )
        except Exception as e:
            logger.error(
                f"Error while stopping monitor for camera {camera.name}: {str(e)}"
            )
            return JsonResponse(
                {"status": "error", "message": "فشل في إيقاف مراقبة الكاميرا"},
                status=500,
            )

    except Exception as e:
        logger.error(f"Error in stop_camera_monitoring: {str(e)}")
        return JsonResponse(
            {"status": "error", "message": "حدث خطأ أثناء إيقاف مراقبة الكاميرا"},
            status=500,
        )


@login_required
def toggle_camera_monitoring(request, camera_id):
    """تبديل حالة مراقبة الكاميرا"""
    try:
        # التحقق من وجود الكاميرا
        try:
            camera = Camera.objects.get(id=camera_id)
        except Camera.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "الكاميرا غير موجودة"}, status=404
            )

        # التحقق من حالة المراقب
        monitor = active_monitors.get(camera_id)
        if monitor and monitor.is_running:
            # إيقاف المراقب
            try:
                monitor.stop_monitoring()  # استخدام stop_monitoring بدلاً من stop
                del active_monitors[camera_id]
                logger.info(
                    f"Stopped monitoring camera {camera.name} (ID: {camera_id})"
                )
                return JsonResponse(
                    {
                        "status": "success",
                        "message": "تم إيقاف مراقبة الكاميرا",
                        "is_monitoring": False,
                    }
                )
            except Exception as e:
                logger.error(f"Error stopping camera {camera.name}: {str(e)}")
                return JsonResponse(
                    {"status": "error", "message": "فشل في إيقاف مراقبة الكاميرا"},
                    status=500,
                )
        else:
            # بدء المراقب
            try:
                monitor = LiveSecurityMonitor(camera_id)
                if monitor.start_monitoring():
                    active_monitors[camera_id] = monitor
                    logger.info(
                        f"Started monitoring camera {camera.name} (ID: {camera_id})"
                    )
                    return JsonResponse(
                        {
                            "status": "success",
                            "message": "تم بدء مراقبة الكاميرا",
                            "is_monitoring": True,
                        }
                    )
                else:
                    return JsonResponse(
                        {"status": "error", "message": "فشل في بدء مراقبة الكاميرا"},
                        status=500,
                    )
            except Exception as e:
                logger.error(f"Error starting camera {camera.name}: {str(e)}")
                return JsonResponse(
                    {"status": "error", "message": "فشل في بدء مراقبة الكاميرا"},
                    status=500,
                )

    except Exception as e:
        logger.error(f"Error in toggle_camera_monitoring: {str(e)}")
        return JsonResponse(
            {"status": "error", "message": "حدث خطأ أثناء تبديل حالة مراقبة الكاميرا"},
            status=500,
        )


@login_required
def video_feed(request):
    """بث فيديو مباشر من الكاميرا (فقط للصفحة الرئيسية)"""
    def gen_frames():
        monitor = None
        if active_monitors:
            monitor = list(active_monitors.values())[0]
        while True:
            frame = None
            if monitor:
                frame = monitor.get_frame()
            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "NO FRAME", (120, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.05)  # معدل إطارات أعلى
    response = StreamingHttpResponse(gen_frames(), content_type='multipart/x-mixed-replace; boundary=frame')
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@login_required
@require_http_methods(["POST"])
def mark_alert_read(request, alert_id):
    """Mark a specific alert as read."""
    try:
        alert = get_object_or_404(Alert, id=alert_id, user=request.user)
        alert.is_read = True
        alert.save()
        return JsonResponse({"success": True, "message": "تم وضع علامة مقروء على التنبيه."}, status=200)
    except Exception as e:
        logger.error(f"Error marking alert {alert_id} as read: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def mark_all_alerts_read(request):
    """Mark all unread alerts for the current user as read."""
    try:
        Alert.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({"success": True, "message": "All unread alerts marked as read."}, status=200)
    except Exception as e:
        logger.error(f"Error marking all alerts as read for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def delete_alert(request, alert_id):
    """Delete a specific alert."""
    try:
        alert = get_object_or_404(Alert, id=alert_id, user=request.user)
        alert.delete()
        return JsonResponse({"success": True, "message": "Alert deleted successfully."}, status=200)
    except Exception as e:
        logger.error(f"Error deleting alert {alert_id}: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_alerts(request):
    """API endpoint to fetch filtered alerts for the alerts page."""
    try:
        severity_filter = request.GET.get('severity', 'all')
        read_filter = request.GET.get('read', 'all')
        date_filter = request.GET.get('date', 'all')

        alerts_qs = Alert.objects.filter(user=request.user).order_by("-timestamp")

        if severity_filter != 'all':
            alerts_qs = alerts_qs.filter(severity__iexact=severity_filter)

        if read_filter != 'all':
            alerts_qs = alerts_qs.filter(is_read=(read_filter == 'read'))

        if date_filter != 'all':
            today = timezone.now().date()
            if date_filter == 'today':
                alerts_qs = alerts_qs.filter(timestamp__date=today)
            elif date_filter == 'week':
                # Filter for the last 7 days including today
                start_of_week = today - timedelta(days=today.weekday())
                alerts_qs = alerts_qs.filter(timestamp__date__gte=start_of_week)
            elif date_filter == 'month':
                # Filter for the current month
                alerts_qs = alerts_qs.filter(timestamp__month=today.month, timestamp__year=today.year)
        
        # Prepare alerts data for JSON response
        alerts_data = []
        for alert in alerts_qs:
            alerts_data.append({
                "id": alert.id,
                "category": alert.get_category_display(),  # Get the display name of the category
                "message": alert.description,
                "timestamp": alert.timestamp.strftime("%Y-%m-%d %H:%M"),
                "severity": alert.get_severity_display(),  # Get the display name of the severity
                "location": alert.camera.location if alert.camera else "غير معروف",
                "confidence": f"{alert.confidence:.2f}",
                "is_read": alert.is_read,
                "camera_name": alert.camera.name if alert.camera else "غير معروف",
            })

        return JsonResponse({"alerts": alerts_data}, status=200)
    except Exception as e:
        logger.error(f"Error in api_alerts: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def api_camera_status(request):
    """API endpoint for camera status"""
    try:
        cameras = Camera.objects.filter(users=request.user)

        cameras_data = []
        for camera in cameras:
            cameras_data.append(
                {
                    "id": camera.id,
                    "name": camera.name,
                    "location": camera.location,
                    "is_active": camera.is_active,
                    "is_monitoring": False,  # Placeholder
                }
            )

        return JsonResponse({"cameras": cameras_data})
    except Exception:
        return JsonResponse({"cameras": []})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def update_notification_settings(request):
    """Update notification settings via AJAX"""
    try:
        data = json.loads(request.body)

        settings, created = NotificationSettings.objects.get_or_create(
            user=request.user
        )

        settings.email_notifications = data.get("email_notifications", False)
        settings.telegram_notifications = data.get("telegram_notifications", False)
        settings.whatsapp_notifications = data.get("whatsapp_notifications", False)
        settings.telegram_username = data.get("telegram_username", "")
        settings.telegram_chat_id = data.get("telegram_chat_id", "")
        settings.whatsapp_number = data.get("whatsapp_number", "")
        settings.selected_model = data.get(
            "selected_model", ""
        )  # Update selected model
        settings.save()

        return JsonResponse({"status": "success", "message": "تم حفظ الإعدادات بنجاح"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def force_camera_scan(request):
    """يكتشف الكاميرات الفعلية ويربطها بالمستخدم"""
    max_cameras = 5  # عدد الكاميرات التي سيتم تجربتها
    found = 0
    for idx in range(max_cameras):
        cap = cv2.VideoCapture(idx)
        if cap is not None and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                # تحقق إن الكاميرا مش موجودة مسبقًا للمستخدم
                cam_qs = Camera.objects.filter(users=request.user, camera_index=idx)
                if not cam_qs.exists():
                    camera = Camera.objects.create(
                        name=f"كاميرا {idx + 1}",
                        location=f"مدخل {idx + 1}",
                        camera_index=idx,
                        is_active=True,
                    )
                    camera.users.add(request.user)
                    found += 1
            cap.release()

    return JsonResponse({
        "message": f"تم اكتشاف {found} كاميرا جديدة."
    })



@csrf_exempt
def send_message(request):
    """API endpoint for sending messages to the chatbot"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get("message")

            if not user_message:
                return JsonResponse({"error": "Message cannot be empty"}, status=400)

            # Pass the user object to the RAG system
            response = rag_system.process_message(user_message, request.user)
            
            return JsonResponse({"response": response})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error in chatbot send_message: {str(e)}")
            return JsonResponse({"error": f"Error generating response: {str(e)}"}, status=500)
    return JsonResponse({"error": "Invalid request method"}, status=405)


@login_required
def chatbot_view(request):
    """عرض صفحة المساعد الذكي (الشات بوت)"""
    return render(request, "dashboard/chatbot.html")


@login_required
def start_monitoring(request):
    """بدء المراقبة الأمنية"""
    try:
        # التحقق من إعدادات الإشعارات
        notification_settings = NotificationSettings.objects.filter(user=request.user).first()
        if not notification_settings or not notification_settings.telegram_chat_id:
            return JsonResponse({
                'status': 'error',
                'message': 'يرجى إعداد إشعارات تيليجرام أولاً'
            })

        # التحقق من وجود النماذج
        try:
            notifier = get_security_notifier()
        except RuntimeError as e:
            return JsonResponse({
                'status': 'error',
                'message': 'لم يتم العثور على نماذج الكشف. يرجى التأكد من وجود ملفات النماذج في المجلد الصحيح.'
            })

        # بدء المراقبة
        asyncio.run(notifier.start_monitoring(request.user))
        
        return JsonResponse({
            'status': 'success',
            'message': 'تم بدء المراقبة بنجاح'
        })
    except Exception as e:
        logger.error(f"Error in start_monitoring: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'حدث خطأ: {str(e)}'
        })


@login_required
def stop_monitoring(request):
    """إيقاف المراقبة الأمنية"""
    try:
        notifier = get_security_notifier()
        asyncio.run(notifier.stop_monitoring())
        
        return JsonResponse({
            'status': 'success',
            'message': 'تم إيقاف المراقبة بنجاح'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'حدث خطأ: {str(e)}'
        })


@login_required
def get_monitoring_status(request):
    """الحصول على حالة المراقبة"""
    try:
        notifier = get_security_notifier()
        return JsonResponse({
            'status': 'success',
            'is_active': notifier.system_active,
            'last_threat': notifier.last_threat,
            'last_threat_time': notifier.last_threat_time.isoformat() if notifier.last_threat_time else None
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'حدث خطأ: {str(e)}'
        })


@login_required
def update_notification_settings(request):
    """تحديث إعدادات الإشعارات"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            telegram_chat_id = data.get('telegram_chat_id')
            
            # تحديث أو إنشاء إعدادات الإشعارات
            settings, created = NotificationSettings.objects.get_or_create(user=request.user)
            settings.telegram_chat_id = telegram_chat_id
            settings.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'تم تحديث إعدادات الإشعارات بنجاح'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'حدث خطأ: {str(e)}'
            })
    return JsonResponse({
        'status': 'error',
        'message': 'طريقة طلب غير صالحة'
    })
