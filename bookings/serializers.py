from rest_framework import serializers
from django.db import IntegrityError, transaction
from .models import Appointment
from .validators import validate_slot_is_bookable
from rest_framework.exceptions import ValidationError as DRFValidationError


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

class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ["id", "doctor", "patient", "start_time", "end_time", "status"]
        read_only_fields = ["id", "end_time", "status"]
        validators = []

    def validate(self, data):
        doctor = data["doctor"]
        start_time = data["start_time"]

        end_time = validate_slot_is_bookable(doctor, start_time)
        data["end_time"] = end_time
        return data

    def create(self, validated_data):
        with transaction.atomic():
            return Appointment.objects.create(**validated_data)
        