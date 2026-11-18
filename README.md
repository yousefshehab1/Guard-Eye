<p align="center">
  <img src="assets/logo.jpg" alt="Guard Eye logo - Eyes that think. Security that acts." width="420">
</p>

# Guard Eye - AI Surveillance Camera System

Graduation project, Faculty of Artificial Intelligence, Menoufia University (class of 2025).

A Django web application for monitoring camera feeds with AI-based threat detection, alert management, and multi-channel notifications. This repository is a clean re-upload of the team's original project with secrets removed and configuration moved to environment variables. Original repository: https://github.com/Ziadshehata1/Surveillance-Camera-

## What the code does

- **Camera management**: add cameras (local index or stream URL), activate/deactivate them, and start/stop monitoring from a web dashboard (`dashboard/views.py`, `dashboard/models.py`).
- **Detection scripts**: standalone OpenCV/Ultralytics scripts for fire, weapon, and violence detection (`fire_detection_system.py`, `weapon_detection_system.py`, `vio_detection_system.py`), each sending frames to the Google Gemini API for scene analysis.
- **Gemini security analysis**: `all_models.py` sends frames to Gemini (2.0 Flash) with a structured prompt to classify violence, masked-person, fire, gun, and theft events with bounding boxes and a threat level.
- **Alerts**: detections are stored as `Alert` records (severity, category, image) and listed/filtered in the dashboard; a WebSocket consumer (`security_system/consumers.py`, Django Channels) pushes live alert messages.
- **Notifications**: email via SMTP, Telegram bot messages/photos (`dashboard/notifications.py`, `dashboard/utils.py`), and a WhatsApp sending stub. Per-user preferences in `NotificationSettings`.
- **Analytics**: an analytics dashboard aggregating alerts by category, severity, and time (`dashboard/analytics_views.py`).
- **RAG chatbot**: `dashboard/rag_system.py` indexes stored alerts in FAISS with HuggingFace embeddings (`sayed0am/arabic-english-bge-m3`) and answers questions about them with a Groq LLM (`llama-3.3-70b-versatile`), with Arabic support.
- **Auth**: signup, login/logout, and password reset via Django auth and the included templates.

## Project structure

```
manage.py                  Django entry point
security_system/           Django project (settings, urls, asgi/wsgi, websocket consumer)
dashboard/                 Main app: models, views, templates, notifications, RAG, live monitor
all_models.py              Gemini-based frame analysis (used by the live monitor)
fire_detection_system.py   Standalone fire detection script
weapon_detection_system.py Standalone weapon detection script
vio_detection_system.py    Standalone violence detection script
static/                    CSS/JS assets
src/                       Unused React/Next.js prototype fragment (not wired into the app)
Procfile, render.yaml      Render deployment config
```

## Setup

1. Python 3.12, then `pip install -r requirements.txt` (note: the requirements list is a broad, unpinned dump of the team's dev environment; install what you actually need).
2. Copy `.env.example` to `security_system/.env` and fill in your own keys (see below).
3. Configure PostgreSQL (or edit `DATABASES` in `security_system/settings.py` for SQLite).
4. `python manage.py migrate && python manage.py runserver`.

Required environment variables for full functionality: `SECRET_KEY`, database settings, `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` (SMTP), `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, `GEMINI_API_KEY` (frame analysis and detection scripts), `GROQ_API_KEY` and `HUGGINGFACE_API_KEY` (RAG chatbot).

## Honest status and known limitations

- **Trained model weights (`.pt`) are not included.** `AI_MODELS` in settings and `YOLO_MODEL_PATH` expect local weight files.
- `dashboard/live_security_monitor.py` imports a local `models.all_models` package and `all_models.py` imports `security_system.utils`; these helper modules are not in this repository, so the live monitoring loop does not run as-is.
- The WhatsApp notification path is a placeholder (`WHATSAPP_API_KEY` was never a real integration).
- `DEBUG = True` and `ALLOWED_HOSTS = ["*"]` in settings: this is a student project, not production-ready.
- `src/` is an abandoned React prototype and is not part of the running app.
- No automated tests; `dashboard/tests.py` and `dashboard/test_cameras.py` are manual scratch scripts.

## Security note

The original repository accidentally committed a `.env` file containing live credentials (a Telegram bot token, an email password, and a Django secret key). Anyone who cloned the original repository must treat those credentials as compromised and rotate them (revoke the Telegram bot token, change the email password, and regenerate the Django secret key). This copy keeps all secrets in environment variables (see `.env.example`).

## Team

- [Yousef Shehab](https://github.com/yousefshehab1) - team leader
- [Ziad Shehata](https://github.com/Ziadshehata1) - original repository owner
- [ivark013](https://github.com/ivark013) - contributor
