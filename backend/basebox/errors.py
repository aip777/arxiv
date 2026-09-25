import logging
import re
import traceback

from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

SECRET_RE = re.compile(
    r"(password|passwd|token|secret|api[_-]?key|authorization)[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}\]]+",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    return SECRET_RE.sub(r"\1=***", text)


def api_exception_handler(exc, context):
    """
    Put validation errors under `detail` like every other error. Anything DRF
    does not handle is re-raised, so Django logs it and answers with handler500.
    """
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, ValidationError):
        response.data = {"detail": response.data}
    return response


class DatabaseLogHandler(logging.Handler):
    """Copies log records into the ErrorLog table so they can be browsed in the admin."""

    def emit(self, record):
        from basebox.models import ErrorLog

        request = getattr(record, "request", None)
        trace = "".join(traceback.format_exception(*record.exc_info)) if record.exc_info else None
        try:
            ErrorLog.objects.create(
                level=record.levelname,
                message=redact(record.getMessage())[:2000],
                traceback=redact(trace)[:10000] if trace else None,
                path=getattr(request, "path", None),
                method=getattr(request, "method", None),
                status_code=getattr(record, "status_code", None),
            )
        except Exception:
            self.handleError(record)
