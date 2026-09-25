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

SQLITE_PATH = Path(config("SQLITE_PATH", default=str(BASE_DIR / "data" / "arxiv.sqlite3")))
SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
        "OPTIONS": {
            "timeout": 20,
            # WAL lets the API keep reading while an ingestion run is writing.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            # Take the write lock up front to avoid "database is locked" upgrade errors.
            "transaction_mode": "IMMEDIATE",
        },
    }
}

# File-based so the /ask rate limit is shared by all gunicorn workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": SQLITE_PATH.parent / "cache",
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
# Always passed explicitly: an empty OPENAI_BASE_URL in the environment would otherwise
# be picked up by the SDK itself and break every request.
OPENAI_BASE_URL = config("OPENAI_BASE_URL", default="") or "https://api.openai.com/v1"
# Changing the model makes every stored vector stale; the next index sync re-embeds them.
EMBEDDING_MODEL = config("EMBEDDING_MODEL", default="text-embedding-3-small")
EMBEDDING_BATCH_SIZE = config("EMBEDDING_BATCH_SIZE", default=100, cast=int)
LLM_MODEL = config("LLM_MODEL", default="gpt-4.1-mini")
LLM_TIMEOUT = config("LLM_TIMEOUT", default=60, cast=int)
RAG_TOP_K = config("RAG_TOP_K", default=5, cast=int)
# Cosine distance (0 = identical, 2 = opposite). Hits further away than this are ignored.
RAG_MAX_DISTANCE = config("RAG_MAX_DISTANCE", default=0.65, cast=float)

REST_FRAMEWORK = {
    # The API is public and read-only apart from /ask, so no authentication is configured.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="300/minute"),
        # /ask calls a paid LLM, so it gets a tighter limit.
        "ask": config("THROTTLE_ASK", default="20/minute"),
    },
    "EXCEPTION_HANDLER": "basebox.errors.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "arXiv Papers API",
    "DESCRIPTION": "Aggregated statistics and RAG question answering over arXiv papers.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

LOG_LEVEL = config("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}.{funcName}:{lineno} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        # Errors also go to the ErrorLog table, which is browsable in the admin.
        "database": {"class": "basebox.errors.DatabaseLogHandler", "level": "ERROR"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # Unhandled exceptions in views, with the request that caused them.
        "django.request": {"handlers": ["console", "database"], "level": "ERROR", "propagate": False},
        **{
            app: {"handlers": ["console", "database"], "level": LOG_LEVEL, "propagate": False}
            for app in ("basebox", "papers", "rag")
        },
    },
}
