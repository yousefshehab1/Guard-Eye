import logging
import requests
from django.conf import settings
from django.core.mail import send_mail
from .models import Alert, NotificationSettings
import asyncio
import cv2
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Union
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import signal
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import threading
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import error as telegram_error
from ultralytics import YOLO
import numpy as np
from .utils import get_camera_instance

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class SingletonMeta(type):
    _instances = {}
    _lock = asyncio.Lock()
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]
    
    @classmethod
    async def cleanup_instance(cls, instance_cls):
        async with cls._lock:
            if instance_cls in cls._instances:
                instance = cls._instances[instance_cls]
                await instance.cleanup()
                del cls._instances[instance_cls]

class SecurityNotifier(metaclass=SingletonMeta):
    """
    نظام إرسال الإشعارات الأمنية
    """
    def __init__(self):
        self.bot = None
        self.system_active = False
        self.frame_buffer = []
        self.buffer_size = 30  # تخزين 3 ثواني من الفيديو بمعدل 10 إطارات في الثانية
        self.detector = SurveillanceDetector()
        self.last_alert = None
        self.last_threat = None
        self.last_threat_time = None
        self.surveillance_task = None
        self._cleanup_lock = asyncio.Lock()
        self._is_cleaning_up = False
        self.initialize_bot()

    def initialize_bot(self):
        """تهيئة بوت تيليجرام"""
        try:
            bot_token = settings.TELEGRAM_BOT_TOKEN
            if not bot_token:
                logger.error("TELEGRAM_BOT_TOKEN not found in settings")
                return
            self.bot = Bot(token=bot_token)
            logger.info("Telegram bot initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing bot: {e}")

    async def cleanup(self):
        """تنظيف الموارد وإيقاف جميع المهام"""
        async with self._cleanup_lock:
            if self._is_cleaning_up:
                return
            self._is_cleaning_up = True
            
            logger.info("Cleaning up resources...")
            self.system_active = False
            
            if self.surveillance_task and not self.surveillance_task.done():
                self.surveillance_task.cancel()
                try:
                    await self.surveillance_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("Cleanup completed")
            self._is_cleaning_up = False

    async def start_monitoring(self, user):
        """بدء المراقبة للمستخدم المحدد"""
        try:
            if not self.system_active:
                self.system_active = True
                self.surveillance_task = asyncio.create_task(self.process_video_feed(user))
                logger.info(f"Started monitoring for user: {user.username}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error starting monitoring: {e}")
            return False

    async def stop_monitoring(self):
        """إيقاف المراقبة"""
        try:
            if self.system_active:
                self.system_active = False
                if self.surveillance_task and not self.surveillance_task.done():
                    self.surveillance_task.cancel()
                    try:
                        await self.surveillance_task
                    except asyncio.CancelledError:
                        pass
                logger.info("Monitoring stopped")
                return True
            return False
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")
            return False

    async def process_video_feed(self, user):
        """معالجة بث الفيديو من الكاميرا"""
        cap = None
        try:
            cap = get_camera_instance()
            if not cap.isOpened():
                logger.error("Could not open camera")
                return

            logger.info("Starting video surveillance...")
            
            while self.system_active:
                ret, frame = cap.read()
                if not ret:
                    logger.error("Could not read frame")
                    break

                # إضافة الإطار إلى المخزن المؤقت
                self.frame_buffer.append(frame.copy())
                if len(self.frame_buffer) > self.buffer_size:
                    self.frame_buffer.pop(0)

                # تشغيل الكشف على الإطار
                detections = self.detector.detect_objects(frame)
                
                if detections:
                    # حفظ فيديو التنبيه مع الكشف
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    video_path = os.path.join(settings.MEDIA_ROOT, "alerts", f"alert_{timestamp}.mp4")
                    os.makedirs(os.path.dirname(video_path), exist_ok=True)
                    
                    self.detector.save_alert_video(self.frame_buffer, detections, video_path)
                    
                    # إرسال التنبيه
                    await self.send_security_alert(user, detections, video_path)

                # تأخير صغير لمنع استخدام وحدة المعالجة المركزية بشكل مفرط
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("Surveillance task cancelled")
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}")
        finally:
            if cap:
                cap.release()
            logger.info("Video surveillance stopped")

    async def send_security_alert(self, user, detections: List[Dict], video_path: str):
        """إرسال تنبيه أمني إلى المستخدم"""
        try:
            if not user.telegram_chat_id:
                logger.warning(f"No telegram chat ID for user {user.username}")
                return

            # الحصول على الكشف الرئيسي
            primary_detection = max(detections, key=lambda x: x["confidence"])
            
            # تخزين معلومات آخر تهديد
            self.last_threat = primary_detection
            self.last_threat_time = datetime.now()
            
            # إنشاء رسالة التنبيه باللغة العربية
            alert_message = f"""
🚨 **تنبيه أمني عاجل** 🚨

📅 **التاريخ والوقت:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🎯 **نوع التهديد:** {self.get_arabic_threat_type(primary_detection["type"])}
📊 **مستوى الثقة:** {primary_detection["confidence"]:.1%}

📹 **مقطع الفيديو مرفق أدناه**
            """
            
            # إرسال الفيديو مع التعليق
            with open(video_path, 'rb') as video_file:
                await self.bot.send_video(
                    chat_id=user.telegram_chat_id,
                    video=video_file,
                    caption=alert_message,
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error sending alert: {str(e)}")

    def get_arabic_threat_type(self, threat_type: str) -> str:
        """تحويل نوع التهديد من الإنجليزية إلى العربية"""
        arabic_types = {
            "weapons": "أسلحة خطيرة",
            "fire": "حريق", 
            "violence": "عنف أو اعتداء"
        }
        return arabic_types.get(threat_type, "تهديد غير محدد")

class SurveillanceDetector:
    """
    نظام كشف الأمان باستخدام الرؤية الحاسوبية
    """
    def __init__(self):
        # تحميل النماذج المدربة مسبقاً
        current_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(current_dir, "models")
        
        # التأكد من وجود مجلد النماذج
        if not os.path.exists(models_dir):
            os.makedirs(models_dir)
            logger.warning(f"Created models directory at {models_dir}")
        
        # قائمة النماذج المطلوبة
        required_models = {
            "weapons": "best_weapon.pt",
            "fire": "bestfire.pt",
            "violence": "vio_best.pt"
        }
        
        # تحميل النماذج المتوفرة فقط
        self.models = {}
        for model_type, model_file in required_models.items():
            model_path = os.path.join(models_dir, model_file)
            if os.path.exists(model_path):
                try:
                    self.models[model_type] = YOLO(model_path)
                    logger.info(f"Loaded {model_type} model successfully")
                except Exception as e:
                    logger.error(f"Error loading {model_type} model: {e}")
            else:
                logger.warning(f"Model file not found: {model_path}")
        
        if not self.models:
            logger.error("No models were loaded successfully")
            raise RuntimeError("No detection models available")
        
        # عتبات الكشف
        self.thresholds = {
            "weapons": 0.5,
            "fire": 0.4,
            "violence": 0.6
        }

        # تعريف الفئات المستهدفة لكل نموذج
        self.target_classes = {
            "weapons": ["knife", "gun"],
            "fire": ["fire", "smoke"],
            "violence": ["violence"]
        }

    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """تشغيل الكشف على الإطار وإرجاع النتائج"""
        detections = []
        
        for detection_type, model in self.models.items():
            try:
                results = model(frame)
                
                for result in results:
                    boxes = result.boxes
                    if boxes is not None and len(boxes) > 0:
                        for box in boxes:
                            confidence = float(box.conf[0])
                            class_id = int(box.cls[0])
                            class_name = model.names[class_id]
                            
                            if (class_name in self.target_classes[detection_type] and 
                                confidence >= self.thresholds[detection_type]):
                                
                                x1, y1, x2, y2 = box.xyxy[0].tolist()
                                
                                detection = {
                                    "type": detection_type,
                                    "class": class_name,
                                    "confidence": confidence,
                                    "bbox": [x1, y1, x2, y2],
                                    "timestamp": datetime.now().isoformat(),
                                    "area": (x2-x1) * (y2-y1)
                                }
                                detections.append(detection)
                                logger.info(f"Detected {class_name} ({detection_type}) with confidence {confidence:.2f}")
                                
            except Exception as e:
                logger.error(f"Error in {detection_type} detection: {e}")
                
        return detections

    def save_alert_video(self, frames: List[np.ndarray], detections: List[Dict], output_path: str):
        """حفظ مقطع فيديو مع تعليقات الكشف"""
        if not frames:
            return
            
        height, width = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, 10.0, (width, height))
        
        try:
            font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arial.ttf")
            if not os.path.exists(font_path):
                logger.warning("Arial font not found, downloading...")
                import requests
                font_url = "https://github.com/microsoft/fonts/raw/master/arial.ttf"
                response = requests.get(font_url)
                with open(font_path, 'wb') as f:
                    f.write(response.content)
            font = ImageFont.truetype(font_path, 20)
        except Exception as e:
            logger.error(f"Error loading font: {e}")
            font = ImageFont.load_default()
        
        for frame in frames:
            frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(frame_pil)
            
            for detection in detections:
                x1, y1, x2, y2 = map(int, detection["bbox"])
                detection_type = detection["type"]
                class_name = detection["class"]
                confidence = detection["confidence"]
                
                colors = {
                    "weapons": (255, 0, 0),    # Red
                    "fire": (255, 165, 0),     # Orange
                    "violence": (255, 255, 0),  # Yellow
                }
                
                color = colors.get(detection_type, (255, 255, 255))
                
                draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                
                label = f"{class_name.upper()}: {confidence:.2f}"
                
                text_bbox = draw.textbbox((0, 0), label, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                draw.rectangle(
                    [x1, y1 - text_height - 4, x1 + text_width, y1],
                    fill=color,
                    outline=color
                )
                
                draw.text(
                    (x1, y1 - text_height - 2),
                    label,
                    fill=(0, 0, 0),
                    font=font
                )
            
            frame_cv2 = cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)
            out.write(frame_cv2)
        
        out.release()

# إنشاء نسخة وحيدة من المراقب
security_notifier = SecurityNotifier()

def get_security_notifier():
    """الحصول على نسخة المراقب"""
    return security_notifier

def send_notifications(alert):
    """
    Send notifications for an alert through all enabled channels.
    
    Args:
        alert (Alert): The alert object to send notifications for
    """
    try:
        # Get notification settings for the user
        notification_settings = NotificationSettings.objects.get(user=alert.camera.user)
        
        # Send email notification if enabled
        if notification_settings.email_notifications:
            send_email_notification(alert)
        
        # Send Telegram notification if enabled
        if notification_settings.telegram_notifications and notification_settings.telegram_chat_id:
            send_telegram_notification(alert, notification_settings.telegram_chat_id)
        
        # Send WhatsApp notification if enabled
        if notification_settings.whatsapp_notifications and notification_settings.whatsapp_number:
            send_whatsapp_notification(alert, notification_settings.whatsapp_number)
            
    except Exception as e:
        logger.error(f"Error sending notifications: {str(e)}")

def send_email_notification(alert):
    """
    Send email notification for an alert.
    
    Args:
        alert (Alert): The alert object
    """
    try:
        subject = f"تنبيه أمني: {alert.description}"
        message = f"""
        تم اكتشاف تهديد أمني:
        
        الكاميرا: {alert.camera.name}
        الوصف: {alert.description}
        مستوى الخطورة: {alert.get_severity_display()}
        الوقت: {alert.timestamp}
        """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [alert.camera.user.email],
            fail_silently=False,
        )
        logger.info(f"Email notification sent for alert {alert.id}")
        
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")

def send_telegram_notification(alert, chat_id):
    """
    Send Telegram notification for an alert.
    
    Args:
        alert (Alert): The alert object
        chat_id (str): The Telegram chat ID to send the notification to
    """
    try:
        # Get the bot token from settings
        bot_token = settings.TELEGRAM_BOT_TOKEN
        
        if not bot_token:
            logger.error("Telegram bot token not configured")
            return False

        # Prepare the message text
        message = f"""
*تنبيه أمني*
الكاميرا: {alert.camera.name}
الوصف: {alert.description}
مستوى الخطورة: {alert.get_severity_display()}
الوقت: {alert.timestamp}
"""
        
        # Escape special characters for MarkdownV2
        message = escape_markdown_v2(message)

        # Send photo if available
        if alert.image:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(alert.image.path, "rb") as photo:
                files = {"photo": photo}
                data = {"chat_id": chat_id, "caption": message, "parse_mode": "MarkdownV2"}
                response = requests.post(url, data=data, files=files)
                if response.status_code != 200:
                    logger.error(f"Failed to send Telegram photo: {response.text}")
                    return False
                logger.info(f"Telegram photo notification sent for alert {alert.id}")
                return True
        else:
            # Send text-only message
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
            response = requests.post(url, data=data)
            if response.status_code != 200:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False
            logger.info(f"Telegram text notification sent for alert {alert.id}")
            return True
            
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {str(e)}")
        return False

def send_whatsapp_notification(alert, phone_number):
    """
    Send WhatsApp notification for an alert.
    
    Args:
        alert (Alert): The alert object
        phone_number (str): The WhatsApp number to send the notification to
    """
    try:
        # Get the WhatsApp API token from settings
        whatsapp_token = settings.WHATSAPP_TOKEN
        
        if not whatsapp_token:
            logger.error("WhatsApp token not configured")
            return False

        # Prepare the message
        message = f"""
تنبيه أمني:
الكاميرا: {alert.camera.name}
الوصف: {alert.description}
مستوى الخطورة: {alert.get_severity_display()}
الوقت: {alert.timestamp}
"""
        
        # Send message using WhatsApp API
        url = f"https://graph.facebook.com/v13.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {whatsapp_token}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": message}
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            logger.error(f"Failed to send WhatsApp message: {response.text}")
            return False
            
        logger.info(f"WhatsApp notification sent for alert {alert.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp notification: {str(e)}")
        return False

def escape_markdown_v2(text: str) -> str:
    """
    Escape characters in the input that have special meaning in Telegram's MarkdownV2.
    
    Args:
        text (str): The text to escape
        
    Returns:
        str: The escaped text
    """
    # Characters that need to be escaped in MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    escaped_text = ""
    for char in text:
        if char in escape_chars:
            escaped_text += "\\" + char
        else:
            escaped_text += char
    return escaped_text 