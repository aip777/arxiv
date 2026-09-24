from decouple import config

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
    "EXCEPTION_HANDLER": "basebox.utils.exceptions.custom_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "arXiv Papers API",
    "DESCRIPTION": "Aggregated statistics and RAG question answering over arXiv papers.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
