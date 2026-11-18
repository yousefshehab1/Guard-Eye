import cv2
import threading
import time
import logging
import os
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from dotenv import load_dotenv
from django.contrib.auth.models import User
from .notifications import send_telegram_notification
from models.all_models import SecurityAnalyzer
import numpy as np
from .utils import get_camera_instance

# تحميل متغيرات البيئة
load_dotenv()

# إعداد التسجيل
logger = logging.getLogger(__name__)

# المسار الأساسي لحفظ صور التنبيهات
ALERTS_BASE_DIR = os.path.join(settings.MEDIA_ROOT, "alerts")
os.makedirs(ALERTS_BASE_DIR, exist_ok=True)

def save_alert_image(frame, category="other", severity="medium"):
    """حفظ صورة التنبيه في المجلد المناسب"""
    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        save_dir = os.path.join(ALERTS_BASE_DIR, date_str, category.lower(), severity.lower())
        os.makedirs(save_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%H-%M-%S-%f")[:-3]
        filename = f"alert_{timestamp}.jpg"
        abs_path = os.path.join(save_dir, filename)

        if cv2.imwrite(abs_path, frame):
            rel_path = os.path.join("alerts", date_str, category.lower(), severity.lower(), filename)
            rel_path = rel_path.replace("\\", "/")
            logger.info(f"Image saved successfully at: {rel_path}")
            return rel_path
        return None
    except Exception as e:
        logger.error(f"Error saving alert image: {str(e)}")
        return None

def create_alert(user, camera, threats, frame):
    """إنشاء تنبيه جديد في قاعدة البيانات"""
    from .models import Alert
    if not threats:
        return None

    try:
        main_threat = max(threats, key=lambda t: t.get('confidence', 0))
        main_category = main_threat.get("category", "other")
        highest_confidence = main_threat.get("confidence", 0)
        highest_severity = main_threat.get("severity", "medium")
        description = main_threat.get("description", f"تم اكتشاف: {main_category}")

        alert = Alert.objects.create(
            user=user,
            camera=camera,
            description=description,
            severity=highest_severity,
            category=main_category,
            confidence=highest_confidence,
            timestamp=timezone.now()
        )

        saved_image_path = save_alert_image(frame, main_category, highest_severity)
        if saved_image_path:
            alert.image.name = saved_image_path
            alert.save()

        return alert
    except Exception as e:
        logger.error(f"Error creating alert: {str(e)}")
        return None

class LiveSecurityMonitor:
    """فئة لمراقبة الأمن المباشر"""
    
    def __init__(self, camera_id):
        self.camera_id = camera_id
        self.camera = None
        self.is_running = False
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.target_fps = 15
        self.last_frame_time = time.time()
        self.detection_thread = None
        self.fps = 0
        self.frame_count = 0
        self.fps_update_interval = 1.0
        self.last_fps_update = time.time()
        self.last_real_frame = None  # جديد: لتخزين آخر إطار حقيقي
        
        # تهيئة محلل الأمن
        self.analyzer = SecurityAnalyzer(confidence_threshold=70)
        logger.info("تم تهيئة محلل الأمن بنجاح")

    def get_frame(self):
        with self.frame_lock:
            if self.current_frame is not None and self.current_frame.size > 0:
                return self.current_frame.copy()
            elif self.last_real_frame is not None:
                return self.last_real_frame.copy()
            else:
                # صورة سوداء فقط إذا لم يوجد أي إطار حقيقي
                placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder,
                    "WAITING FOR FRAME",
                    (120, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                return placeholder

    def start_monitoring(self):
        """بدء مراقبة الكاميرا"""
        if self.is_running:
            return True
            
        if not self._reconnect_camera():
            return False
            
        self.is_running = True
        self.detection_thread = threading.Thread(target=self._run_detection)
        self.detection_thread.daemon = True
        self.detection_thread.start()
        logger.info(f"بدأت مراقبة الكاميرا {self.camera_id}")
        return True

    def stop_monitoring(self):
        """إيقاف مراقبة الكاميرا"""
        self.is_running = False
        if self.detection_thread and self.detection_thread.is_alive():
            if threading.current_thread() != self.detection_thread:
                self.detection_thread.join(timeout=5.0)
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        logger.info(f"توقفت مراقبة الكاميرا {self.camera_id}")
        return True

    def _reconnect_camera(self):
        """إعادة الاتصال بالكاميرا"""
        try:
            if self.camera is not None:
                self.camera.release()
            camera_index = 0
            logger.warning(f"Trying to open camera with index: {camera_index}")
            self.camera = get_camera_instance()

            if not self.camera.isOpened():
                logger.error(f"❌ فشل في فتح الكاميرا رقم {camera_index}")
                return False
            else:
                logger.info(f"✅ تم فتح الكاميرا رقم {camera_index} بنجاح")
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.camera.set(cv2.CAP_PROP_FPS, self.target_fps)
            return True
        except Exception as e:
            logger.error(f"Error reconnecting to camera: {str(e)}")
            return False

    def _run_detection(self):
        try:
            while self.is_running:
                self._process_frame()  # عالج إطار دائمًا
                # التحكم في معدل الإطارات
                elapsed = time.time() - self.last_frame_time
                if elapsed < 1.0/self.target_fps:
                    time.sleep(1.0/self.target_fps - elapsed)
                self.last_frame_time = time.time()
        except Exception as e:
            logger.error(f"Error in detection loop: {str(e)}")
        finally:
            logger.info(f"Detection loop finished for camera {self.camera_id}")
            self.stop_monitoring()

    def _process_frame(self):
        if self.camera is None or not self.camera.isOpened():
            current_time = time.time()
            if not hasattr(self, '_last_connection_warning') or current_time - self._last_connection_warning > 5:
                logger.warning(f"Camera {self.camera_id} not opened. Attempting to reconnect...")
                self._last_connection_warning = current_time
            with self.frame_lock:
                self.current_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    self.current_frame,
                    "CAMERA OFFLINE",
                    (120, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    2,
                    (0, 0, 255),
                    3,
                )
            time.sleep(0.1)
            return self._reconnect_camera()
        ret, frame = self.camera.read()
        if ret and frame is not None:
            self.last_real_frame = frame.copy()  # جديد: خزّن آخر إطار حقيقي
        if not ret or frame is None:
            current_time = time.time()
            if not hasattr(self, '_last_frame_warning') or current_time - self._last_frame_warning > 5:
                logger.warning(f"Failed to read frame from camera {self.camera_id}. Setting placeholder frame.")
                self._last_frame_warning = current_time
            with self.frame_lock:
                self.current_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    self.current_frame,
                    "FRAME READ FAILED",
                    (120, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    2,
                    (0, 0, 255),
                    3,
                )
            time.sleep(0.05)
            return False
        if frame.shape[0] == 0 or frame.shape[1] == 0:
            logger.warning(f"Invalid frame dimensions: {frame.shape}")
            time.sleep(0.05)
            return False
        frame = cv2.resize(frame, (640, 480))
        frame = cv2.GaussianBlur(frame, (5, 5), 0)
        self._update_fps()
        try:
            annotated_frame, analysis_result = self.analyzer.process_frame(frame)
            with self.frame_lock:
                self.current_frame = annotated_frame
            if analysis_result and analysis_result.get("detected_threats"):
                self._handle_detected_threats(analysis_result, annotated_frame)
        except Exception as e:
            logger.error(f"Error processing frame with analyzer: {str(e)}", exc_info=True)
            with self.frame_lock:
                self.current_frame = frame.copy()
        return True

    def _update_fps(self):
        """تحديث معدل الإطارات"""
        current_time = time.time()
        self.frame_count += 1
        if current_time - self.last_fps_update >= self.fps_update_interval:
            self.fps = self.frame_count / (current_time - self.last_fps_update)
            self.frame_count = 0
            self.last_fps_update = current_time
            
        cv2.putText(self.current_frame, f"FPS: {self.fps:.1f}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    def _handle_detected_threats(self, analysis_result, frame):
        """معالجة التهديدات المكتشفة"""
        try:
            user_instance = User.objects.get(id=1)
            camera_instance = self.get_camera_instance()
            
            if camera_instance:
                alert = create_alert(
                    user_instance,
                    camera_instance,
                    analysis_result["detected_threats"],
                    frame
                )
                
                if alert:
                    self._send_notifications(alert)
                    
        except Exception as e:
            logger.error(f"Error handling detected threats: {str(e)}")

    def _send_notifications(self, alert):
        """إرسال التنبيهات"""
        try:
            notification_settings = self.get_notification_settings(alert.user)
            if notification_settings and notification_settings.telegram_notifications:
                send_telegram_notification(alert, notification_settings.telegram_chat_id)
        except Exception as e:
            logger.error(f"Error sending notifications: {str(e)}")

    def get_camera_instance(self):
        """الحصول على كائن الكاميرا من قاعدة البيانات"""
        from .models import Camera
        try:
            return Camera.objects.get(id=self.camera_id)
        except Camera.DoesNotExist:
            logger.error(f"Camera {self.camera_id} not found in database")
            return None

    def get_notification_settings(self, user):
        """الحصول على إعدادات التنبيهات للمستخدم"""
        from .models import NotificationSettings
        try:
            return NotificationSettings.objects.get(user=user)
        except NotificationSettings.DoesNotExist:
            return None

    def _open_camera(self):
        camera_index = 0  # اجبار استخدام الكاميرا رقم 0
        logging.warning(f"Trying to open camera with index: {camera_index}")
        self.camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            logging.error(f"❌ فشل في فتح الكاميرا رقم {camera_index}")
        else:
            logging.info(f"✅ تم فتح الكاميرا رقم {camera_index} بنجاح")