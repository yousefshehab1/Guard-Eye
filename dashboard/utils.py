import cv2
import numpy as np
import os
import time
import logging
import requests
import torch
import yaml
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail
from typing import List, Tuple
from .models import Camera
from dotenv import load_dotenv
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# Add Telegram settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

logger = logging.getLogger(__name__)

# تكوين المسارات
MEDIA_ROOT = getattr(settings, "MEDIA_ROOT", "media")
ALERTS_DIR = os.path.join(MEDIA_ROOT, "alerts")

# التأكد من وجود المجلدات
os.makedirs(ALERTS_DIR, exist_ok=True)

# قاموس الأوصاف العربية لأنواع التهديدات
THREAT_DESCRIPTIONS_ARABIC = {
    "violence": "اكتشاف عنف",
    "thief_mask": "اكتشاف شخص يرتدي قناعاً (سرقة محتملة)",
    "fire": "اكتشاف حريق",
    "gun": "اكتشاف سلاح ناري",
    "theft": "اكتشاف نشاط سرقة محتمل",
    "other": "تهديد غير مصنف",  # في حال عدم تحديد فئة
}

_camera_instance = None

def get_camera_instance():
    global _camera_instance
    if _camera_instance is None or not _camera_instance.isOpened():
        _camera_instance = cv2.VideoCapture(0)
    return _camera_instance

def send_telegram_message(chat_id: str, message: str, image_path: str = None):
    """
    Send a message to a Telegram chat.

    Args:
        chat_id (str): The chat ID to send the message to
        message (str): The message text
        image_path (str, optional): Path to an image file to send

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        # Get the bot token from settings
        bot_token = settings.TELEGRAM_BOT_TOKEN

        if not bot_token:
            logger.error("Telegram bot token not configured")
            return False

        # Prepare the message text
        message = escape_markdown_v2(message)

        # Send photo or text message
        if image_path and os.path.exists(image_path):
            logger.info(f"Sending Telegram photo to chat {chat_id} from {image_path}")
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(image_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": chat_id,
                    "caption": message,
                    "parse_mode": "MarkdownV2",
                }
                response = requests.post(url, data=data, files=files)
                if response.status_code != 200:
                    logger.error(f"Failed to send Telegram photo: {response.text}")
                    return False
                logger.info(f"Telegram photo sent successfully to {chat_id}")
                return True
        else:
            if image_path:
                logger.error(f"Telegram image file not found at: {image_path}")
                return False
            # Send text-only message
            logger.info(f"Sending Telegram text notification to chat {chat_id}")
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
            response = requests.post(url, data=data)
            if response.status_code != 200:
                logger.error(
                    f"Failed to send Telegram message. Status code: {response.status_code}, Response: {response.text}"
                )
                return False
            logger.info(f"Telegram message sent successfully to {chat_id}")
            return True
    except Exception as e:
        logger.error(f"Error in send_telegram_message: {str(e)}")
        return False


def get_telegram_chat_id(username: str) -> str:
    """
    Get the numeric chat ID for a Telegram username.

    Args:
        username (str): The Telegram username (with or without @)

    Returns:
        str: The numeric chat ID if found, None otherwise
    """
    try:
        # Remove @ if present
        username = username.lstrip("@")

        # Get the bot token from settings
        bot_token = settings.TELEGRAM_BOT_TOKEN

        if not bot_token:
            logger.error("Telegram bot token not configured")
            return None

        # First, try to get chat ID using getChat method
        url = f"https://api.telegram.org/bot{bot_token}/getChat"
        data = {"chat_id": f"@{username}"}

        response = requests.post(url, data=data)

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                return str(result["result"]["id"])

        # If getChat fails, try to get updates and find the chat ID
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        response = requests.get(url)

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                for update in result["result"]:
                    if "message" in update:
                        message = update["message"]
                        if "chat" in message:
                            chat = message["chat"]
                            if chat.get("username") == username:
                                return str(chat["id"])

        logger.error(f"Could not find chat ID for username {username}")
        return None

    except Exception as e:
        logger.error(f"Error getting Telegram chat ID: {str(e)}")
        return None


def detect_available_cameras() -> List[Tuple[int, bool]]:
    """
    Detects locally available cameras with improved error handling and device change detection.
    Returns a list of tuples: (camera_index, is_connected)
    """
    available_cameras = []
    backends = [
        (cv2.CAP_MSMF, "MSMF"),  # Windows Media Foundation
        (cv2.CAP_DSHOW, "DSHOW"),  # DirectShow (Windows)
        (cv2.CAP_ANY, "ANY"),  # Auto-detect
    ]

    for i in range(10):  # Check first 10 indices
        camera_connected = False
        last_error = None
        best_backend = None

        for backend, backend_name in backends:
            cap = None
            try:
                logger.info(f"Trying camera {i} with {backend_name} backend")
                cap = cv2.VideoCapture(i, backend)

                if cap.isOpened():
                    # Set camera properties with error checking
                    properties = {
                        cv2.CAP_PROP_FRAME_WIDTH: 640,
                        cv2.CAP_PROP_FRAME_HEIGHT: 480,
                        cv2.CAP_PROP_FPS: 15,
                        cv2.CAP_PROP_BUFFERSIZE: 1,
                        cv2.CAP_PROP_AUTOFOCUS: 1,
                        cv2.CAP_PROP_AUTO_EXPOSURE: 1
                    }
                    
                    for prop, value in properties.items():
                        if not cap.set(prop, value):
                            logger.warning(f"Failed to set property {prop} for camera {i}")

                    # Try to read multiple frames to ensure stability
                    frames_read = 0
                    for _ in range(3):  # Try reading 3 frames
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            frames_read += 1
                            time.sleep(0.1)  # Small delay between reads
                    
                    if frames_read >= 2:  # At least 2 successful frame reads
                        camera_connected = True
                        best_backend = backend_name
                        logger.info(f"Found stable camera at index {i} using {backend_name} backend")
                        break
                    else:
                        logger.warning(f"Camera {i} opened with {backend_name} but frame reading was unstable")
                else:
                    logger.debug(f"Camera {i} could not be opened with {backend_name}")
            except Exception as e:
                last_error = e
                logger.error(f"Error checking camera {i} with {backend_name}: {e}")
            finally:
                if cap and cap.isOpened():
                    cap.release()
                    time.sleep(0.1)  # Small delay after releasing camera

        if camera_connected:
            logger.info(f"Camera {i} is available and stable using {best_backend} backend")
        else:
            logger.warning(f"Camera {i} is not available or unstable. Last error: {last_error}")
        
        available_cameras.append((i, camera_connected))

    return available_cameras


def create_error_frame(message):
    """Creates a simple error frame with a message."""
    img = np.zeros((480, 640, 3), np.uint8)
    cv2.putText(
        img,
        message,
        (50, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )
    return img


def create_error_image():
    """إنشاء صورة خطأ بسيطة."""
    # إنشاء صورة سوداء
    img = np.zeros((480, 640, 3), np.uint8)

    # كتابة نص الخطأ باللغة الإنجليزية لتجنب مشاكل الترميز
    cv2.putText(
        img,
        "Camera Not Connected",
        (150, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
    )

    # تحويل الصورة إلى JPEG
    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


def create_camera_off_image():
    """إنشاء صورة توضح أن الكاميرا متوقفة."""
    img = np.zeros((480, 640, 3), np.uint8)
    cv2.putText(
        img,
        "Camera Is Off",
        (200, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 255),
        2,
    )
    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


def update_camera_database():
    """Updates the database with currently available cameras."""
    connected_cameras = detect_available_cameras()

    # Deactivate all cameras first
    Camera.objects.update(is_active=False)

    for cam_index, is_connected in connected_cameras:
        if is_connected:
            # Find or create the camera
            camera, created = Camera.objects.get_or_create(
                camera_index=cam_index,
                defaults={
                    "name": f"Local Camera {cam_index}",
                    "location": f"Location {cam_index}",
                    "is_active": True
                }
            )
            if not created:
                camera.is_active = True
                camera.save()
                logger.info(f"Camera {cam_index} activated.")
            else:
                logger.info(f"Camera {cam_index} not connected.")


def save_image_from_frame(frame, alert_instance, detection_type, severity):
    try:
        # Ensure frame is a numpy array
        if not isinstance(frame, np.ndarray):
            logger.error("Invalid frame type for saving image. Expected numpy.ndarray.")
            return

        # Convert the frame (which is BGR from OpenCV) to RGB for PIL
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)

        # Create a directory for detected images if it doesn't exist
        detection_dir = os.path.join(
            settings.MEDIA_ROOT, "detections", detection_type.lower()
        )
        if not os.path.exists(detection_dir):
            os.makedirs(detection_dir)

        # Generate filename based on timestamp, detection type, and severity
        timestamp_str = alert_instance.timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{detection_type.lower()}_{severity.lower()}.jpg"
        filepath = os.path.join(detection_dir, filename)

        # Save the image using PIL
        pil_image.save(filepath, format="JPEG")

        # Update the alert instance with the saved image path
        relative_path = os.path.join("detections", detection_type.lower(), filename)
        alert_instance.image.name = relative_path
        alert_instance.save()
        logger.info(
            f"Image saved successfully for alert {alert_instance.id} at {relative_path}"
        )
    except Exception as e:
        logger.error(f"Error saving image for alert {alert_instance.id}: {e}")


def escape_markdown_v2(text: str) -> str:
    """
    Escapes characters in the input that have special meaning in Telegram's MarkdownV2.
    """
    # Characters that need to be escaped in MarkdownV2
    # _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    escaped_text = ""
    for char in text:
        if char in escape_chars:
            escaped_text += "\\" + char
        else:
            escaped_text += char
    return escaped_text


monitor_instance = None


def detect_objects(frame):
    """كشف الأشياء في الإطار باستخدام النموذج المختار من إعدادات الإشعارات."""
    try:
        global monitor_instance
        if monitor_instance is None:
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from security_monitoring_system_updated import create_security_monitor

            monitor_instance = create_security_monitor()
        monitor = monitor_instance

        if monitor is None or monitor.model is None:
            logger.warning(
                "Security monitor or model not initialized. Returning original frame."
            )
            return frame, []

        # معالجة الإطار باستخدام النموذج الحالي للمراقب
        processed_frame, detections = monitor.process_frame(frame)

        # تحويل النتائج إلى قائمة بسيطة إذا لزم الأمر (process_frame يجب أن يعيدها بهذا التنسيق)
        detection_list = []
        for det in detections:
            detection_list.append(
                {
                    "class": det["class"],
                    "confidence": float(det["confidence"]),
                    "box": det["box"],
                }
            )

        return processed_frame, detection_list

    except Exception as e:
        logger.error(f"حدث خطأ أثناء كشف الأشياء: {str(e)}")
        return frame, []
