import logging

from django.db import connection
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    throttle_classes = []

    @extend_schema(exclude=True)
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            logger.exception("Health check failed: database unreachable")
            return Response({"status": "error", "database": "unreachable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok", "database": "ok"})


def not_found(request, exception=None):
    return JsonResponse({"detail": "Not found."}, status=404)


def server_error(request):
    return JsonResponse({"detail": "An unexpected error occurred."}, status=500)
