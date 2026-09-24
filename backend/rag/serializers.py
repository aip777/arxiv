from rest_framework import serializers


class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=3, max_length=1000, trim_whitespace=True)
    top_k = serializers.IntegerField(min_value=1, max_value=20, required=False)


class SourceSerializer(serializers.Serializer):
    arxiv_id = serializers.CharField()
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    primary_category = serializers.CharField()
    published = serializers.DateField()
    url = serializers.URLField()
    similarity = serializers.FloatField(help_text="Cosine similarity between question and paper (0-1).")


class AskResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    sources = SourceSerializer(many=True)
