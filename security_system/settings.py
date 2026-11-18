import os
from pathlib import Path
import dj_database_url
import torch


# Try loading dotenv only if available
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")


DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dashboard",
    "corsheaders",
    "dj_database_url",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]

ROOT_URLCONF = "security_system.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / 'templates',
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "security_system.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "serveliance",
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "OPTIONS": {
            "client_encoding": "UTF8"
        }
    }
}

# لا تستخدم DATABASE_URL الآن
# DATABASE_URL = os.getenv("DATABASE_URL")
# if DATABASE_URL:
#     DATABASES["default"] = dj_database_url.config(default=DATABASE_URL)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

ALLOWED_HOSTS = ["*"]

LANGUAGE_CODE = "ar"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

CSRF_TRUSTED_ORIGINS = [
    o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]


MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email settings (replace with your actual email settings)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

# Telegram settings (replace with your actual Telegram bot token)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# WhatsApp settings (you'll need to implement this using a third-party service)
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")
WHATSAPP_DEFAULT_NUMBER = os.getenv("WHATSAPP_DEFAULT_NUMBER", "")
# AI model paths
AI_MODELS = {
    'yolo': {
        'model': os.path.join(BASE_DIR, "models", "yolov9c.pt"),
        'yaml': os.path.join(BASE_DIR, "models", "yolov9c.yaml"),
        'classes': ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat']  # أضف باقي الأصناف حسب الحاجة
    },
    'thief_mask': {
        'model': os.path.join(BASE_DIR, "models", "theif-mask detection 2.pt"),
        'yaml': os.path.join(BASE_DIR, "models", "theif-mask detection 2.yaml"),
        'classes': ['يرتدي قناع', 'لا يرتدي قناع']
    },
    'weapon': {
        'model': os.path.join(BASE_DIR, "models", "gun-knife detection 2.pt"),
        'yaml': os.path.join(BASE_DIR, "models", "weapon_data.yaml"),
        'classes': ['مسدس', 'سكين', 'سلاح']
    },
    'violence': {
        'model': os.path.join(BASE_DIR, "models", "vio_best2.pt"),
        'yaml': os.path.join(BASE_DIR, "models", "violence_data.yaml"),
        'classes': ['عنف', 'تجمع مشبوه']
    },
    'thief': {
        'model': os.path.join(BASE_DIR, "models", "thief.pt"),
        'yaml': os.path.join(BASE_DIR, "models", "thief_data.yaml"),
        'classes': ['شخص مشبوه', 'نشاط مشبوه']
    }
}

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Database encoding settings
DEFAULT_CHARSET = 'utf-8'
FILE_CHARSET = 'utf-8'

# Force UTF-8 encoding for all database operations
DATABASE_OPTIONS = {
    'charset': 'utf8',
    'use_unicode': True,
}

# Set the default encoding for the application
DEFAULT_CHARSET = 'utf-8'
FILE_CHARSET = 'utf-8'

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'dashboard': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# AI/LLM settings (referenced by all_models.py and dashboard/rag_system.py)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "")
GEMINI_API_KEY_3 = os.getenv("GEMINI_API_KEY_3", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", os.path.join(BASE_DIR, "models", "best.pt"))
