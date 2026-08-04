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

class AppointmentCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": "A cancellation reason is required.",
            "blank": "Cancellation reason cannot be blank.",
        },
    )

    def validate(self, data):
        appointment = self.context["appointment"]
        if appointment.status == Appointment.Status.CANCELLED:
            raise DRFValidationError({"status": "This appointment is already cancelled."})
        return data

    def save(self):
        appointment = self.context["appointment"]
        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = self.validated_data["cancellation_reason"]
        appointment.full_clean()  # runs Appointment.clean() — belt-and-suspenders check
        appointment.save()
        return appointment