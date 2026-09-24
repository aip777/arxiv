from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY", default="django-insecure-local-dev-only")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "basebox",
    "papers",
    "rag",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "basebox.middlewares.error_logging_middleware.ErrorLoggingMiddleware",
]

ROOT_URLCONF = "pconfig.urls"
WSGI_APPLICATION = "pconfig.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="arxiv"),
        "USER": config("POSTGRES_USER", default="arxiv"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="arxiv"),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- arXiv ingestion -------------------------------------------------------
ARXIV_API_URL = config("ARXIV_API_URL", default="https://export.arxiv.org/api/query")
ARXIV_CATEGORIES = config("ARXIV_CATEGORIES", default="cs.AI,cs.LG,cs.CL", cast=Csv())
ARXIV_REQUEST_DELAY = config("ARXIV_REQUEST_DELAY", default=3.0, cast=float)
ARXIV_PAGE_SIZE = config("ARXIV_PAGE_SIZE", default=100, cast=int)
ARXIV_MAX_RETRIES = config("ARXIV_MAX_RETRIES", default=5, cast=int)
ARXIV_TIMEOUT = config("ARXIV_TIMEOUT", default=60, cast=int)

# --- RAG ---------------------------------------------------------------------
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = config("OPENAI_BASE_URL", default="") or None
# The vector column is 1536-dimensional (rag.models.EMBEDDING_DIMENSIONS); the model must produce that size.
EMBEDDING_MODEL = config("EMBEDDING_MODEL", default="text-embedding-3-small")
EMBEDDING_BATCH_SIZE = config("EMBEDDING_BATCH_SIZE", default=100, cast=int)
LLM_MODEL = config("LLM_MODEL", default="gpt-4o-mini")
LLM_TIMEOUT = config("LLM_TIMEOUT", default=60, cast=int)
RAG_TOP_K = config("RAG_TOP_K", default=5, cast=int)
# Cosine distance (0 = identical, 2 = opposite). Hits further away than this are ignored.
RAG_MAX_DISTANCE = config("RAG_MAX_DISTANCE", default=0.65, cast=float)

from pconfig.logs_config import *  # noqa: E402,F401,F403
from pconfig.rest_config import *  # noqa: E402,F401,F403
