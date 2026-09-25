import logging

from django.db import DatabaseError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from basebox.utils.error_logger import create_error_log, extract_request_info

logger = logging.getLogger(__name__)


def _mark_logged(request):
    """Tell ErrorLoggingMiddleware this request has already been recorded."""
    if not request:
        return
    request._error_logged = True
    django_request = getattr(request, "_request", None)
    if django_request is not None:
        django_request._error_logged = True


def custom_exception_handler(exc, context):
    """
    Return every API error as JSON with a `detail` key and record it in ErrorLog.

    Validation errors keep DRF's per-field structure under `detail` so clients can
    point at the offending parameter.
    """
    request = context.get("request")
    path, method, user = extract_request_info(request)
    _mark_logged(request)

    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, ValidationError):
            response.data = {"detail": response.data}
        level = "ERROR" if response.status_code >= 500 else "WARNING"
        create_error_log(
            level=level,
            message=str(response.data.get("detail", exc)),
            exc=exc if response.status_code >= 500 else None,
            path=path,
            method=method,
            user=user,
            status_code=response.status_code,
        )
        return response

    if isinstance(exc, DatabaseError):
        message = "A database error occurred. Please try again later."
    else:
        message = "An unexpected error occurred."

    logger.error("Unhandled error on %s %s: %s", method, path, exc, exc_info=exc)
    return Response({"detail": message}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
