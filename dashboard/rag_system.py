from django.conf import settings
import os
import json
import torch
from ultralytics import YOLO
from langchain_groq import ChatGroq
from langchain.schema import Document
from langchain.prompts import ChatPromptTemplate
from langchain.schema import SystemMessage, HumanMessage
from langchain.chains import LLMChain
from langchain.schema.runnable import RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
import numpy as np
from datetime import datetime
import logging
from dashboard.models import Alert
from django.utils import timezone

logger = logging.getLogger(__name__)

class SurveillanceRAGSystem:
    def __init__(self):
        """Initialize RAG system with Groq LLM"""
        try:
            # Set up API keys from Django settings
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = settings.HUGGINGFACE_API_KEY
            os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY
            
            # Initialize YOLO model for object detection
            self.yolo_model = YOLO(settings.YOLO_MODEL_PATH)
            
            # Initialize Groq LLM with the correct available model
            self.llm = ChatGroq(
                api_key=settings.GROQ_API_KEY,
                model_name="llama-3.3-70b-versatile",  # Using available production model
                temperature=0.7,
                max_tokens=1024
            )
            
            # Initialize embedding model
            self.embedding = HuggingFaceEmbeddings(
                model_name="sayed0am/arabic-english-bge-m3",
                model_kwargs={"device": "cuda" if torch.cuda.is_available() else "cpu"},
                encode_kwargs={"normalize_embeddings": True}
            )
            
            # Initialize vector store
            self.vector_store = self._initialize_vector_store()
            
            # Initialize retriever
            self.retriever = self.vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 3}
            )
            
            # Initialize prompt template with Arabic support
            self.prompt = ChatPromptTemplate.from_messages([
                ("system", """أنت مساعد ذكي لنظام الأمن. استخدم السياق التالي للمساعدة في الإجابة على السؤال:
                {context}
                
                إذا كنت لا تعرف الإجابة، قل ببساطة أنك لا تعرف. لا تحاول اختلاق إجابة."""),
                ("human", "{question}")
            ])
            
            # Initialize chain
            self.chain = (
                {"context": self.retriever, "question": RunnablePassthrough()}
                | self.prompt
                | self.llm
            )
            
            # Detection history for context
            self.detection_history = []
            
            print("RAG system initialized successfully")
            
        except Exception as e:
            print(f"Error initializing RAG system: {str(e)}")
            raise

    def _initialize_vector_store(self):
        """Initialize the vector store with security data"""
        try:
            # Create some initial security-related documents
            security_docs = [
                Document(
                    page_content="Security protocol for unauthorized access: Alert security personnel and lock down affected areas.",
                    metadata={"source": "security_protocols", "type": "access_control"}
                ),
                Document(
                    page_content="Emergency response procedure: Evacuate area, contact emergency services, and secure perimeter.",
                    metadata={"source": "emergency_procedures", "type": "response"}
                ),
                Document(
                    page_content="Suspicious activity protocol: Document details, notify authorities, and maintain surveillance.",
                    metadata={"source": "security_protocols", "type": "surveillance"}
                )
            ]
            
            # Create and return the vector store
            return FAISS.from_documents(security_docs, self.embedding)
            
        except Exception as e:
            print(f"Error initializing vector store: {str(e)}")
            raise

    def get_security_data(self):
        """Fetch security data from the database"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        incident_type,
                        description,
                        location,
                        timestamp,
                        severity,
                        response_taken
                    FROM security_incidents
                    ORDER BY timestamp DESC
                    LIMIT 100
                """)
                columns = [col[0] for col in cursor.description]
                incidents = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            return incidents
        except Exception as e:
            print(f"Warning: Could not fetch security incidents: {str(e)}")
            return []
    
    def setup_knowledge_base(self):
        """Create knowledge base with security protocols and database incidents"""
        
        # Get security incidents from database
        incidents = self.get_security_data()
        
        # Convert incidents to documents
        documents = []
        
        # Add security protocols
        security_protocols = [
            {
                "content": """
                WEAPON DETECTION PROTOCOLS:
                
                Knife Detection:
                - Immediate alert to security personnel
                - Record timestamp and location
                - Activate lockdown procedures if in restricted area
                - Contact law enforcement if threat level is high
                - Document incident for investigation
                """,
                "source": "Weapon Detection Protocol",
                "category": "weapons"
            },
            {
                "content": """
                FIREARM DETECTION PROTOCOLS:
                
                Gun Detection:
                - IMMEDIATE emergency alert
                - Automatic notification to law enforcement
                - Initiate emergency lockdown procedures
                - Evacuate personnel from immediate area
                - Activate emergency communication systems
                """,
                "source": "Firearm Security Protocol",
                "category": "weapons"
            },
            {
                "content": """
                VIOLENCE DETECTION PROTOCOLS:
                
                Violence/Fighting Detection:
                - Alert security to intervene
                - Record incident for investigation
                - Assess if medical assistance needed
                - Document all parties involved
                - Check for potential weapons
                """,
                "source": "Violence Response Protocol",
                "category": "violence"
            }
        ]
        
        # Add protocols to documents
        for protocol in security_protocols:
            documents.append(Document(
                page_content=protocol["content"],
                metadata={
                    "source": protocol["source"],
                    "category": protocol["category"]
                }
            ))
        
        # Add incidents to documents
        for incident in incidents:
            incident_text = f"""
            Incident Type: {incident['incident_type']}
            Location: {incident['location']}
            Time: {incident['timestamp']}
            Severity: {incident['severity']}
            Description: {incident['description']}
            Response: {incident['response_taken']}
            """
            
            documents.append(Document(
                page_content=incident_text,
                metadata={
                    "source": "Database Incident",
                    "category": incident['incident_type'],
                    "timestamp": incident['timestamp']
                }
            ))
        
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            separators=["\n\n", "\n", " ", ""]
        )
        
        splits = text_splitter.split_documents(documents)
        
        # Create vector store
        self.vectorstore = FAISS.from_documents(splits, self.embedding)
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})
    
    def get_today_alerts_count(self, user):
        today = timezone.now().date()
        return Alert.objects.filter(user=user, timestamp__date=today).count()

    def get_today_high_severity_count(self, user):
        today = timezone.now().date()
        return Alert.objects.filter(user=user, timestamp__date=today, severity='high').count()

    def process_message(self, message, user, location="Main System"):
        """Process user message and provide intelligent response"""
        try:
            # الرد على الأسئلة المتعلقة بعدد التنبيهات اليوم
            if ("عدد التنبيهات" in message or "كل التنبيهات" in message) and "اليوم" in message:
                count = self.get_today_alerts_count(user)
                return f"عدد كل التنبيهات اليوم: {count}"
            if ("عدد التنبيهات" in message or "تنبيهات خطيرة" in message or "عالية الخطورة" in message) and "اليوم" in message:
                count = self.get_today_high_severity_count(user)
                return f"عدد التنبيهات عالية الخطورة اليوم: {count}"

            # Create a simple message format with Arabic support
            formatted_message = f"المستخدم: {message}\nالمساعد:"
            
            # Get response directly from LLM
            response = self.llm.invoke(formatted_message)
            
            # Convert response to string
            if isinstance(response, str):
                return response
            elif hasattr(response, 'content'):
                return response.content
            elif isinstance(response, (dict, list)):
                import json
                return json.dumps(response, ensure_ascii=False, indent=2)
            else:
                return str(response)
                
        except Exception as e:
            print(f"Error in process_message: {str(e)}")
            return f"عذراً، حدث خطأ في معالجة رسالتك. يرجى المحاولة مرة أخرى."
    
    def detect_objects(self, frame):
        """Run YOLO detection on frame"""
        results = self.yolo_model(frame)
        detections = []
        
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.yolo_model.names[class_id]
                    
                    detection = {
                        'class': class_name,
                        'confidence': float(confidence),
                        'bbox': [int(x1), int(y1), int(x2), int(y2)],
                        'timestamp': datetime.now().isoformat()
                    }
                    detections.append(detection)
        
        return detections, results
    
    def analyze_incident(self, detection_info, location="Camera 1", question=None):
        """Analyze detected incident using RAG system"""
        
        if question is None:
            question = f"What should be the security response for detecting {detection_info['class']} with {detection_info['confidence']:.2f} confidence?"
        
        # Prepare context for RAG
        context_data = {
            "detection_info": f"{detection_info['class']} detected",
            "timestamp": detection_info['timestamp'],
            "location": location,
            "confidence": f"{detection_info['confidence']:.2f}",
            "question": question
        }
        
        # Get RAG response
        try:
            response = self.chain.invoke(context_data)
            return response
        except Exception as e:
            return f"Error generating analysis: {str(e)}" 