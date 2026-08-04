from rest_framework import serializers
from django.db import IntegrityError, transaction
from .models import Appointment
from .validators import validate_slot_is_bookable, SlotConflictError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError

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

class AppointmentCancelSerializer(serializers.ModelSerializer):
    cancellation_reason = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": "A cancellation reason is required.",
            "blank": "Cancellation reason cannot be blank.",
        },
    )

    class Meta:
        model = Appointment
        fields = ["cancellation_reason"]

    def validate(self, data):
        if self.instance.status == Appointment.Status.CANCELLED:
            raise DRFValidationError({"status": "This appointment is already cancelled."})
        return data

    def update(self, instance, validated_data):
        instance.status = Appointment.Status.CANCELLED
        instance.cancellation_reason = validated_data["cancellation_reason"]
        try:
            instance.full_clean()
        except DjangoValidationError as e:
            raise DRFValidationError(getattr(e, "message_dict", {"non_field_errors": e.messages}))
        instance.save()
        return instance

class AppointmentRescheduleSerializer(serializers.ModelSerializer):
    start_time = serializers.DateTimeField(required=True)

    class Meta:
        model = Appointment
        fields = ["start_time"]

    def validate(self, data):
        if self.instance.status == Appointment.Status.CANCELLED:
            raise DRFValidationError({"status": "Cannot reschedule a cancelled appointment."})

        doctor = self.instance.doctor
        new_start_time = data["start_time"]
        end_time = validate_slot_is_bookable(doctor, new_start_time)
        data["end_time"] = end_time
        return data

    def update(self, instance, validated_data):
        instance.start_time = validated_data["start_time"]
        instance.end_time = validated_data["end_time"]

        try:
            instance.full_clean()
        except DjangoValidationError as e:
            if "unique_booked_doctor_slot" in str(e):
                raise SlotConflictError()
            raise DRFValidationError(getattr(e, "message_dict", {"non_field_errors": e.messages}))

        try:
            instance.save()
        except IntegrityError:
            raise SlotConflictError()

        return instance