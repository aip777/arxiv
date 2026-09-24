from rest_framework import serializers

from papers.services.stats import INTERVALS


class StatsQuerySerializer(serializers.Serializer):
    top_n = serializers.IntegerField(min_value=1, max_value=50, default=10)
    interval = serializers.ChoiceField(choices=INTERVALS, default="month")
    date_from = serializers.DateField(required=False, help_text="Only papers published on/after (YYYY-MM-DD).")
    date_to = serializers.DateField(required=False, help_text="Only papers published on/before (YYYY-MM-DD).")

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({"date_from": "date_from must be on or before date_to."})
        return attrs
