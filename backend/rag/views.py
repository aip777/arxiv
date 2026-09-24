import logging

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from rag.serializers import AskRequestSerializer, AskResponseSerializer
from rag.services.llm import LLMUnavailable
from rag.services.qa import IndexEmpty, answer_question

logger = logging.getLogger(__name__)


class AskView(APIView):
    throttle_scope = "ask"

    @extend_schema(
        request=AskRequestSerializer,
        responses={200: AskResponseSerializer},
        examples=[OpenApiExample("Question", value={"question": "How are LLM agents evaluated?"},
                                 request_only=True)],
        summary="Answer a question from the paper abstracts (RAG)",
    )
    def post(self, request):
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]
        top_k = serializer.validated_data.get("top_k")

        try:
            result = answer_question(question, top_k=top_k)
        except IndexEmpty as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except LLMUnavailable as exc:
            logger.error("Could not answer question: %s", exc)
            return Response(
                {"detail": "The language model is currently unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result)
