from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from papers.serializers import StatsQuerySerializer
from papers.services.stats import build_stats


class StatsView(APIView):
    """Chart-ready aggregates over the stored papers."""

    @extend_schema(
        parameters=[StatsQuerySerializer],
        responses={200: OpenApiTypes.OBJECT},
        summary="Aggregated paper statistics for charting",
    )
    def get(self, request):
        query = StatsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(build_stats(**query.validated_data))
