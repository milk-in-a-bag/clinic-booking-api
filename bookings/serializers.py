from rest_framework import serializers


class AvailableSlotSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()

class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.DateField(
        error_messages={
            "invalid": "Invalid date format. Use YYYY-MM-DD.",
            "required": "Query parameter 'date' is required (format: YYYY-MM-DD).",
        }
    )