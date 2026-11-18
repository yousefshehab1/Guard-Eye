import cv2
import numpy as np
from ultralytics import YOLO
import google.generativeai as genai
import base64
import json
import time
from datetime import datetime
import os
from typing import List, Dict, Tuple, Optional
import logging
from django.conf import settings
from ..utils import get_gemini_model
from dashboard.utils import get_camera_instance

class ViolenceDetectionSystem:
    def __init__(self, model_path: str, api_key: str, confidence_threshold: float = 0.5):
        """
        Initialize the Violence Detection System

        Args:
            model_path: Path to YOLO model weights
            api_key: Google Gemini API key
            confidence_threshold: Minimum confidence for YOLO detection
        """
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Initialize YOLO model
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold

        # Initialize Gemini
        try:
            self.gemini_model = get_gemini_model()
            self.logger.info("Successfully initialized Gemini model")
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini model: {str(e)}")
            self.gemini_model = None

        # Detection tracking
        self.detection_history = []
        self.last_alert_time = 0
        self.alert_cooldown = 5  # seconds between alerts
        self.gemini_frame_interval = 1.0 # Send a frame to Gemini every 1.0 seconds (1 frame per second)
        self.last_gemini_time = 0


        self.logger.info("Violence Detection System initialized successfully")

    def encode_image_to_base64(self, image: np.ndarray) -> str:
        """Convert OpenCV image to base64 string for Gemini"""
        _, buffer = cv2.imencode('.jpg', image)
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        return image_base64

    def create_gemini_prompt(self, yolo_confidence: float, bbox_info: Dict) -> str:
        """
        Create a detailed prompt for Gemini analysis

        Args:
            yolo_confidence: YOLO detection confidence
            bbox_info: Bounding box information
        """
        prompt = f"""
        You are an expert security analyst specializing in violence detection for surveillance systems.

        CONTEXT:
        - A YOLO model detected potential violence with {yolo_confidence:.2%} confidence
        - Detection area: {bbox_info['area']:.0f} pixels
        - Position: ({bbox_info['x']:.0f}, {bbox_info['y']:.0f})

        ANALYSIS TASK:
        Please analyze this image for signs of violence or aggressive behavior. Consider:

        1. PHYSICAL VIOLENCE INDICATORS:
           - Fighting, hitting, kicking, pushing
           - Weapons or threatening objects
           - Aggressive body language or postures
           - Multiple people in conflict

        2. BEHAVIORAL CUES:
           - Threatening gestures
           - Aggressive movements
           - Crowd disturbances
           - Unusual gathering patterns

        3. ENVIRONMENTAL FACTORS:
           - Context clues (location, time, setting)
           - Emergency situations
           - Property damage or destruction

        RESPONSE FORMAT:
        Provide your analysis in this JSON structure:
        {{
            "violence_detected": true/false,
            "confidence_level": "high/medium/low",
            "violence_type": "physical_fight/weapon_threat/aggressive_behavior/crowd_disturbance/other/none",
            "severity": "critical/high/medium/low",
            "description": "Detailed description of what you observe",
            "recommended_action": "immediate_response/monitor_closely/false_alarm",
            "key_indicators": ["list", "of", "specific", "observations"],
            "location_context": "description of where this is happening in the frame"
        }}

        Be precise and objective. If you're uncertain, indicate lower confidence levels.
        """
        return prompt

    def analyze_with_gemini(self, image: np.ndarray, yolo_confidence: float, bbox_info: Dict) -> Dict:
        """
        Send image to Gemini for detailed analysis

        Args:
            image: OpenCV image
            yolo_confidence: YOLO detection confidence
            bbox_info: Bounding box information

        Returns:
            Dictionary with Gemini analysis results
        """
        try:
            # Encode image
            image_base64 = self.encode_image_to_base64(image)

            # Create prompt
            prompt = self.create_gemini_prompt(yolo_confidence, bbox_info)

            # Send to Gemini
            response = self.gemini_model.generate_content([
                prompt,
                {
                    'mime_type': 'image/jpeg',
                    'data': image_base64
                }
            ])

            # Parse response
            try:
                # Extract JSON from response
                response_text = response.text
                if '```json' in response_text:
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    json_text = response_text[json_start:json_end]
                else:
                    json_text = response_text

                analysis = json.loads(json_text)
                analysis['gemini_success'] = True

            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                analysis = {
                    'violence_detected': True,
                    'confidence_level': 'medium',
                    'violence_type': 'unknown',
                    'severity': 'medium',
                    'description': response.text,
                    'recommended_action': 'monitor_closely',
                    'key_indicators': ['gemini_analysis_available'],
                    'location_context': 'analysis_available',
                    'gemini_success': False
                }

            return analysis

        except Exception as e:
            self.logger.error(f"Gemini analysis failed: {str(e)}")
            return {
                'violence_detected': True,
                'confidence_level': 'low',
                'violence_type': 'unknown',
                'severity': 'low',
                'description': f"Gemini analysis failed: {str(e)}",
                'recommended_action': 'monitor_closely',
                'key_indicators': ['yolo_detection_only'],
                'location_context': 'unknown',
                'gemini_success': False
            }

    def process_yolo_detections(self, results) -> List[Dict]:
        """Process YOLO detection results"""
        detections = []

        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    conf = box.conf[0].cpu().numpy()
                    if conf >= self.confidence_threshold:
                        # Get bounding box coordinates
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                        detection = {
                            'confidence': float(conf),
                            'bbox': [float(x1), float(y1), float(x2), float(y2)],
                            'x': float((x1 + x2) / 2),
                            'y': float((y1 + y2) / 2),
                            'width': float(x2 - x1),
                            'height': float(y2 - y1),
                            'area': float((x2 - x1) * (y2 - y1))
                        }
                        detections.append(detection)

        return detections

    def draw_detection_overlay(self, frame: np.ndarray, detections: List[Dict],
                             gemini_analyses: List[Dict]) -> np.ndarray:
        """Draw detection overlays on frame"""
        overlay_frame = frame.copy()

        for i, (detection, analysis) in enumerate(zip(detections, gemini_analyses)):
            x1, y1, x2, y2 = [int(coord) for coord in detection['bbox']]

            # Color based on Gemini analysis
            if analysis['violence_detected']:
                severity = analysis.get('severity', 'medium')
                if severity == 'critical':
                    color = (0, 0, 255)  # Red
                elif severity == 'high':
                    color = (0, 100, 255)  # Orange
                else:
                    color = (0, 255, 255)  # Yellow
            else:
                color = (0, 255, 0)  # Green

            # Draw bounding box
            cv2.rectangle(overlay_frame, (x1, y1), (x2, y2), color, 3)

            # Prepare label
            yolo_conf = f"YOLO: {detection['confidence']:.2%}"
            gemini_conf = analysis.get('confidence_level', 'unknown')
            violence_type = analysis.get('violence_type', 'unknown')

            label = f"{yolo_conf} | {gemini_conf} | {violence_type}"

            # Draw label background
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(overlay_frame, (x1, y1 - label_size[1] - 10),
                         (x1 + label_size[0], y1), color, -1)

            # Draw label text
            cv2.putText(overlay_frame, label, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return overlay_frame

    def save_detection_report(self, frame: np.ndarray, detections: List[Dict],
                            analyses: List[Dict], timestamp: str):
        """Save detection report with image and analysis"""
        reports_dir = "violence_reports"
        os.makedirs(reports_dir, exist_ok=True)

        # Save frame
        frame_path = f"{reports_dir}/detection_{timestamp}.jpg"
        cv2.imwrite(frame_path, frame)

        # Create report data
        report_data = {
            'timestamp': timestamp,
            'detections': []
        }

        for detection, analysis in zip(detections, analyses):
            detection_info = {
                'confidence': detection['confidence'],
                'severity': analysis.get('severity', 'medium'),  # Use actual severity from analysis
                'description': analysis.get('description', ''),
                'type': 'violence',
                'location': {
                    'x': detection['x'],
                    'y': detection['y'],
                    'area': detection['area']
                }
            }
            report_data['detections'].append(detection_info)

        # Save report JSON
        report_path = f"{reports_dir}/detection_{timestamp}.json"
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=4)

        return report_path

    def run_live_detection(self, source: int = 0, save_reports: bool = True, show_preview: bool = True):
        """Run live detection on video stream"""
        try:
            camera_index = 0  # اجبار استخدام الكاميرا رقم 0
            logging.warning(f"Trying to open camera with index: {camera_index}")
            cap = get_camera_instance()
            if not cap.isOpened():
                logging.error(f"❌ فشل في فتح الكاميرا رقم {camera_index}")
            else:
                logging.info(f"✅ تم فتح الكاميرا رقم {camera_index} بنجاح")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Run YOLO detection
                results = self.model(frame, verbose=False)
                detections = self.process_yolo_detections(results)

                if detections:
                    # Get current time
                    current_time = time.time()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # Process each detection
                    gemini_analyses = []
                    for detection in detections:
                        # Check if it's time for a new Gemini analysis
                        if current_time - self.last_gemini_time >= self.gemini_frame_interval:
                            analysis = self.analyze_with_gemini(frame, detection['confidence'], detection)
                            gemini_analyses.append(analysis)
                            self.last_gemini_time = current_time
                        else:
                            # Use previous analysis if available
                            if gemini_analyses:
                                gemini_analyses.append(gemini_analyses[-1])
                            else:
                                gemini_analyses.append({
                                    'violence_detected': True,
                                    'confidence_level': 'medium',
                                    'severity': 'medium',
                                    'description': 'Initial detection'
                                })

                    # Draw overlays
                    if show_preview:
                        overlay_frame = self.draw_detection_overlay(frame, detections, gemini_analyses)
                        cv2.imshow('Violence Detection', overlay_frame)

                    # Save report if needed
                    if save_reports and current_time - self.last_alert_time >= self.alert_cooldown:
                        report_path = self.save_detection_report(frame, detections, gemini_analyses, timestamp)
                        self.last_alert_time = current_time

                        # Print simplified detection info
                        for detection, analysis in zip(detections, gemini_analyses):
                            severity = analysis.get('severity', 'medium')
                            confidence = detection['confidence']
                            print(f"\nViolence Detection Alert:")
                            print(f"Type: Violence")
                            print(f"Severity: {severity}")
                            print(f"Confidence: {confidence:.2%}")
                            print(f"Description: {analysis.get('description', 'No description available')}")
                            print("-" * 50)

                if show_preview and cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                time.sleep(2)  # تأخير بين كل كشف

        finally:
            cap.release()
            if show_preview:
                cv2.destroyAllWindows()


# Usage example
def main():
    # Configuration
    MODEL_PATH = 'models/vio_best.pt'  # Changed to vio_best.pt
    API_KEY = 'YOUR_GEMINI_API_KEY' # Replace with your API key or use secrets manager

    # Initialize system
    detector = ViolenceDetectionSystem(
        model_path=MODEL_PATH,
        api_key=API_KEY,
        confidence_threshold=0.6  # Adjust based on your needs
    )

    try:
        results = detector.run_live_detection(
            source=0,  # 0 for default camera, change if using another camera or stream
            save_reports=True,
            show_preview=True
        )

        print("\n" + "="*50)
        print("PROCESSING SUMMARY")
        print("="*50)
        print(f"Frames processed: {results['frames_processed']}")
        print(f"Violence alerts: {results['violence_alerts']}")
        print(f"Alert rate: {results['alert_rate']:.2%}")
        print("="*50)

    except Exception as e:
        print(f"Error processing live stream: {str(e)}")

if __name__ == "__main__":
    main() 