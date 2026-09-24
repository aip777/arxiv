from decouple import config

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
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "db_error": {
            "level": "ERROR",
            "class": "basebox.utils.log_handler.LogHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "basebox": {
            "handlers": ["console", "db_error"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "papers": {
            "handlers": ["console", "db_error"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "rag": {
            "handlers": ["console", "db_error"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
