import cv2
import os
import base64
import time
import json
import requests
from datetime import datetime
from PIL import Image
from io import BytesIO
import numpy as np
import logging
from django.conf import settings
from security_system.utils import get_gemini_model

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security analysis prompt with bounding box information
SECURITY_PROMPT = """
You are a security assistant. Analyze the image for the following specific security threats:
1. Violence (physical fighting, assault, violent confrontations)
2. Thief mask (ski masks, balaclavas, suspicious face coverings)
3. Fire (flames, smoke, burning objects)
4. Guns (any type of firearms)
5. Theft (stealing actions, suspicious handling of belongings)

For each detected threat, provide precise bounding box coordinates in the format [x1, y1, x2, y2] where:
- x1, y1: top-left coordinates (as ratio of image width/height from 0 to 1)
- x2, y2: bottom-right coordinates (as ratio of image width/height from 0 to 1)

Please return a JSON object with the following structure:
{
    "detected_threats": [
        {
            "category": "violence|thief_mask|fire|gun|theft",
            "confidence": 0-100,
            "bounding_box": [x1, y1, x2, y2],
            "description": "brief description of what was detected"
        }
    ],
    "threat_level": "none|low|medium|high",
    "urgent_alerts": ["list of urgent alerts if any"]
}

Provide coordinates as accurate as possible based on the visual elements in the image. If no threats are detected, return an empty array for detected_threats.
"""

class GeminiModel:
    def __init__(self):
        self.api_keys = [
            settings.GEMINI_API_KEY,
            settings.GEMINI_API_KEY_2,
            settings.GEMINI_API_KEY_3
        ]
        self.current_key_index = 0
        self.usage_count = 0
        self.last_reset_time = time.time()
        self.max_requests_per_minute = 60  # الحد الأقصى للطلبات في الدقيقة

    def get_next_key(self):
        """الحصول على المفتاح التالي في الدور"""
        current_time = time.time()
        
        # إعادة تعيين العداد كل دقيقة
        if current_time - self.last_reset_time >= 60:
            self.usage_count = 0
            self.last_reset_time = current_time
        
        # التحقق من تجاوز الحد الأقصى
        if self.usage_count >= self.max_requests_per_minute:
            # الانتقال إلى المفتاح التالي
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            self.usage_count = 0
            self.last_reset_time = current_time
        
        self.usage_count += 1
        return self.api_keys[self.current_key_index]

    def generate_content(self, prompt):
        """إنشاء محتوى باستخدام Gemini مع تناوب المفاتيح"""
        try:
            api_key = self.get_next_key()
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            
            headers = {
                "Content-Type": "application/json"
            }
            
            data = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            response = requests.post(api_url, headers=headers, json=data)
            
            if response.status_code == 429:  # Too Many Requests
                # الانتقال إلى المفتاح التالي عند تجاوز الحد
                self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
                return self.generate_content(prompt)  # إعادة المحاولة مع المفتاح الجديد
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error in Gemini API call: {str(e)}")
            # محاولة استخدام المفتاح التالي في حالة الخطأ
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            return self.generate_content(prompt)  # إعادة المحاولة مع المفتاح الجديد

class SecurityAnalyzer:
    def __init__(self, confidence_threshold=0.5):
        """
        تهيئة محلل الأمان
        
        Args:
            confidence_threshold (float): عتبة الثقة للكشف (0.0 إلى 1.0)
        """
        self.confidence_threshold = confidence_threshold
        
        # تهيئة ألوان مستويات التهديد
        self.threat_level_colors = {
            'high': (0, 0, 255),    # أحمر
            'medium': (0, 165, 255), # برتقالي
            'low': (0, 255, 0),     # أخضر
            'none': (255, 255, 255)  # أبيض
        }
        
        # تهيئة ألوان فئات الكشف
        self.category_colors = {
            'violence': (0, 0, 255),      # أحمر
            'fire': (0, 165, 255),        # برتقالي
            'weapon': (0, 0, 255),        # أحمر
            'theft': (0, 255, 255),       # أصفر
            'theft_mask': (255, 0, 255),  # أرجواني
            'unknown': (128, 128, 128)    # رمادي
        }
        
        # Rate limiting for API calls
        self.last_api_call = 0
        self.api_call_interval = 2.0  # Minimum 2 seconds between API calls
        
        # تهيئة نموذج Gemini
        try:
            self.gemini_model = get_gemini_model()
            logger.info(f"Successfully initialized Gemini model with confidence threshold {confidence_threshold}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {str(e)}")
            self.gemini_model = None

    def encode_image(self, frame):
        """تحويل الإطار إلى ترميز base64"""
        try:
            # تحويل الإطار من BGR إلى RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # تحويل إلى صورة PIL
            pil_image = Image.fromarray(frame_rgb)
            # تحويل إلى bytes
            buffered = BytesIO()
            pil_image.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as e:
            logger.error(f"Error encoding frame: {e}")
            return None

    def analyze_frame(self, frame):
        """تحليل الإطار باستخدام Gemini API"""
        try:
            # Check rate limiting
            current_time = time.time()
            if current_time - self.last_api_call < self.api_call_interval:
                # Return cached result or fallback if rate limited
                return {
                    "threat_level": "low",
                    "detected_threats": [],
                    "description": "Rate limited - using fallback",
                    "confidence": 0.0,
                    "error": "Rate limited"
                }
            
            if not self.gemini_model:
                # Only log this once to reduce spam
                if not hasattr(self, '_logged_no_model'):
                    logger.error("Gemini model not initialized")
                    self._logged_no_model = True
                return {
                    "threat_level": "low",
                    "detected_threats": [],
                    "description": "Model not available",
                    "confidence": 0.0,
                    "error": "Model not initialized"
                }

            # تحويل الإطار إلى base64
            base64_image = self.encode_image(frame)
            if not base64_image:
                return {
                    "threat_level": "low",
                    "detected_threats": [],
                    "description": "Image encoding failed",
                    "confidence": 0.0,
                    "error": "Image encoding failed"
                }

            # تجهيز البيانات للطلب
            prompt = SECURITY_PROMPT
            image_data = {
                'mime_type': 'image/jpeg',
                'data': base64_image
            }

            # Update last API call time
            self.last_api_call = current_time

            # إرسال الطلب
            response = self.gemini_model.generate_content([prompt, image_data])
            
            if response:
                try:
                    # Try to parse the response as JSON
                    response_text = response.text.strip()
                    
                    # Remove any markdown formatting if present
                    if '```json' in response_text:
                        start = response_text.find('```json') + 7
                        end = response_text.find('```', start)
                        if end != -1:
                            response_text = response_text[start:end].strip()
                    elif '```' in response_text:
                        start = response_text.find('```') + 3
                        end = response_text.find('```', start)
                        if end != -1:
                            response_text = response_text[start:end].strip()
                    
                    # Try to find JSON object in the response
                    if '{' in response_text and '}' in response_text:
                        start = response_text.find('{')
                        end = response_text.rfind('}') + 1
                        json_text = response_text[start:end]
                        
                        # Try to parse the JSON
                        analysis = json.loads(json_text)
                        return analysis
                    else:
                        # If no JSON found, create a fallback response
                        if not hasattr(self, '_logged_no_json'):
                            logger.warning("No JSON found in Gemini response, using fallback")
                            self._logged_no_json = True
                        return {
                            "threat_level": "low",
                            "detected_threats": [],
                            "description": "No threats detected",
                            "confidence": 0.1,
                            "gemini_response": response_text[:200]  # First 200 chars for debugging
                        }
                        
                except json.JSONDecodeError as e:
                    # Only log this occasionally to reduce spam
                    current_time = time.time()
                    if not hasattr(self, '_last_json_error') or current_time - self._last_json_error > 30:
                        logger.error(f"Error parsing JSON from Gemini response: {e}")
                        logger.error(f"Response text: {response.text[:500]}...")  # Log first 500 chars
                        self._last_json_error = current_time
                    
                    # Return a fallback response instead of None
                    return {
                        "threat_level": "low",
                        "detected_threats": [],
                        "description": "Analysis failed - using fallback",
                        "confidence": 0.1,
                        "error": "JSON parsing failed"
                    }
            else:
                # Only log this occasionally
                current_time = time.time()
                if not hasattr(self, '_last_empty_response') or current_time - self._last_empty_response > 30:
                    logger.error("Empty response from Gemini API")
                    self._last_empty_response = current_time
                
                return {
                    "threat_level": "low",
                    "detected_threats": [],
                    "description": "No response from API",
                    "confidence": 0.0,
                    "error": "Empty response"
                }
                
        except Exception as e:
            # Handle API quota limits specifically
            if "429" in str(e) or "quota" in str(e).lower():
                # Increase rate limiting interval when quota is exceeded
                self.api_call_interval = min(10.0, self.api_call_interval * 1.5)
                
                # Only log quota errors occasionally
                current_time = time.time()
                if not hasattr(self, '_last_quota_error') or current_time - self._last_quota_error > 60:
                    logger.warning(f"Gemini API quota exceeded: {str(e)[:100]}...")
                    self._last_quota_error = current_time
                
                return {
                    "threat_level": "low",
                    "detected_threats": [],
                    "description": "API quota exceeded - using fallback",
                    "confidence": 0.0,
                    "error": "API quota exceeded"
                }
            else:
                # Only log other errors occasionally
                current_time = time.time()
                if not hasattr(self, '_last_general_error') or current_time - self._last_general_error > 30:
                    logger.error(f"Error analyzing frame: {e}")
                    self._last_general_error = current_time
                
                return {
                    "threat_level": "low",
                    "detected_threats": [],
                    "description": f"Analysis error: {str(e)[:100]}",
                    "confidence": 0.0,
                    "error": str(e)[:100]
                }

    def draw_annotations(self, frame, analysis_result):
        """رسم التعليقات التوضيحية على الإطار"""
        try:
            if not analysis_result:
                return frame
                
            frame_copy = frame.copy()
            height, width = frame_copy.shape[:2]
            
            # إضافة خلفية شفافة للمعلومات النصية
            overlay = frame_copy.copy()
            cv2.rectangle(overlay, (0, 0), (width, 60), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, frame_copy, 0.3, 0, frame_copy)
            
            # إضافة معلومات الأمان
            threat_level = analysis_result.get("threat_level", "none")
            color = self.threat_level_colors.get(threat_level, (0, 255, 0))
            
            # إضافة عنوان
            cv2.putText(frame_copy, "Security Analysis", (10, 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # إضافة مستوى التهديد
            cv2.putText(frame_copy, f"Threat Level: {threat_level.upper()}", (10, 45), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
            # إضافة الطابع الزمني
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame_copy, f"Time: {timestamp}", (width - 200, 45), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            
            # رسم مربعات حول التهديدات المكتشفة
            for threat in analysis_result.get("detected_threats", []):
                confidence = threat.get("confidence", 0)
                
                # عرض التهديدات التي تتجاوز عتبة الثقة
                if confidence >= self.confidence_threshold:
                    category = threat.get("category", "unknown")
                    bbox = threat.get("bounding_box", [0, 0, 0, 0])
                    
                    # تحويل الإحداثيات النسبية إلى إحداثيات البكسل
                    x1 = int(bbox[0] * width)
                    y1 = int(bbox[1] * height)
                    x2 = int(bbox[2] * width)
                    y2 = int(bbox[3] * height)
                    
                    # الحصول على لون التصنيف
                    box_color = self.category_colors.get(category, (0, 255, 0))
                    
                    # رسم المربع
                    cv2.rectangle(frame_copy, (x1, y1), (x2, y2), box_color, 2)
                    
                    # إعداد نص التسمية
                    label = f"{category}: {confidence}%"
                    
                    # رسم خلفية التسمية
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(frame_copy, (x1, y1 - 20), (x1 + label_size[0], y1), box_color, -1)
                    
                    # رسم نص التسمية
                    cv2.putText(frame_copy, label, (x1, y1 - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # إضافة مربع التنبيه إذا كان مستوى التهديد متوسط أو عالي
            if threat_level in ["medium", "high"]:
                thickness = 10 if threat_level == "high" else 5
                cv2.rectangle(frame_copy, (0, 0), (width-1, height-1), color, thickness)
                
                # إضافة نص التنبيه
                y_offset = 80
                for alert in analysis_result.get("urgent_alerts", []):
                    cv2.putText(frame_copy, f"ALERT: {alert}", (10, y_offset), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    y_offset += 25
            
            return frame_copy
            
        except Exception as e:
            # Only log drawing errors occasionally to reduce spam
            current_time = time.time()
            if not hasattr(self, '_last_drawing_error') or current_time - self._last_drawing_error > 60:
                logger.error(f"Error drawing annotations: {e}")
                self._last_drawing_error = current_time
            return frame

    def process_frame(self, frame):
        """معالجة إطار واحد"""
        try:
            # تحليل الإطار
            analysis_result = self.analyze_frame(frame)
            if analysis_result:
                # رسم التعليقات التوضيحية
                annotated_frame = self.draw_annotations(frame, analysis_result)
                
                # طباعة معلومات الكشف في التيرمينال
                threat_level = analysis_result.get("threat_level", "none")
                detected_threats = analysis_result.get("detected_threats", [])
                
                if detected_threats:
                    print("\n" + "="*50)
                    print(f"Threat Level: {threat_level.upper()}")
                    print("="*50)
                    
                    for threat in detected_threats:
                        if threat.get("confidence", 0) >= self.confidence_threshold:
                            category = threat.get("category", "unknown")
                            confidence = threat.get("confidence", 0)
                            description = threat.get("description", "No description")
                            
                            print(f"\nDetection Type: {category.upper()}")
                            print(f"Confidence: {confidence}%")
                            print(f"Description: {description}")
                            print("-"*30)
                    
                    # طباعة التنبيهات العاجلة إذا وجدت
                    urgent_alerts = analysis_result.get("urgent_alerts", [])
                    if urgent_alerts:
                        print("\nURGENT ALERTS:")
                        for alert in urgent_alerts:
                            print(f"- {alert}")
                    
                    print("\n" + "="*50)
                
                return annotated_frame, analysis_result
            return frame, None
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            return frame, None

    def save_detection_report(self, frame, analysis_result, timestamp):
        """حفظ تقرير الكشف"""
        try:
            reports_dir = "security_reports"
            os.makedirs(reports_dir, exist_ok=True)

            # حفظ الصورة
            frame_path = f"{reports_dir}/detection_{timestamp}.jpg"
            cv2.imwrite(frame_path, frame)

            # إنشاء بيانات التقرير
            report_data = {
                'timestamp': timestamp,
                'threat_level': analysis_result.get("threat_level", "none"),
                'detections': []
            }

            # إضافة الكشوفات
            for threat in analysis_result.get("detected_threats", []):
                if threat.get("confidence", 0) >= self.confidence_threshold:
                    detection_info = {
                        'type': threat.get("category", "unknown"),
                        'confidence': threat.get("confidence", 0),
                        'description': threat.get("description", ""),
                        'bounding_box': threat.get("bounding_box", [0, 0, 0, 0])
                    }
                    report_data['detections'].append(detection_info)

            # إضافة التنبيهات العاجلة
            report_data['urgent_alerts'] = analysis_result.get("urgent_alerts", [])

            # حفظ التقرير
            report_path = f"{reports_dir}/detection_{timestamp}.json"
            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=4)

            return report_path
        except Exception as e:
            logger.error(f"Error saving detection report: {e}")
            return None 