from rest_framework import serializers
from django.db import IntegrityError, transaction
from .models import Appointment
from .validators import validate_slot_is_bookable, SlotConflictError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError


def _is_slot_conflict(django_validation_error):
    """
    Checks a DjangoValidationError's structured error_dict for the
    slot-uniqueness violation, using the explicit violation_error_code
    set on Appointment's UniqueConstraint (see models.py) rather than
    string-matching the error message.
    """
    error_dict = getattr(django_validation_error, "error_dict", {})
    return any(
        getattr(err, "code", None) == "unique_booked_doctor_slot"
        for errors in error_dict.values()
        for err in errors
    )


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


class AppointmentResponseSerializer(serializers.ModelSerializer):
    """
    Shared read-only serializer for appointment responses, used by the
    create, cancel, and reschedule views so all three return a consistently
    shaped payload instead of each view hand-building its own dict.
    """
    class Meta:
        model = Appointment
        fields = ["id", "doctor", "patient", "start_time", "end_time", "status", "cancellation_reason"]


class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ["id", "doctor", "patient", "start_time", "end_time", "status"]
        read_only_fields = ["id", "end_time", "status"]
        # Disables DRF's auto-generated UniqueConstraint validator (the only
        # validator this would otherwise add). We deliberately rely on the DB
        # constraint + IntegrityError -> 409 instead, since a serializer-level
        # uniqueness check can't catch true concurrent-request races. This does
        # NOT affect Appointment.clean() (not auto-invoked by ModelSerializer
        # regardless of this setting).
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
            # Defensive backstop: not currently reachable as a failure via this
            # endpoint (the check above and the required reason field already
            # cover clean()'s two rules), but guards against future changes to
            # Appointment.clean() introducing a rule this serializer doesn't know about.
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
        # Same validation a fresh booking would go through: not in the past,
        # lands on a real slot boundary within working hours.
        end_time = validate_slot_is_bookable(doctor, new_start_time)
        data["end_time"] = end_time
        return data

    def update(self, instance, validated_data):
        instance.start_time = validated_data["start_time"]
        instance.end_time = validated_data["end_time"]

        try:
            instance.full_clean()
        except DjangoValidationError as e:
            if _is_slot_conflict(e):
                raise SlotConflictError()
            raise DRFValidationError(getattr(e, "message_dict", {"non_field_errors": e.messages}))

        try:
            instance.save()
        except IntegrityError:
            # Belt-and-suspenders: covers the true race-condition case where
            # a conflicting booking commits between full_clean() and save().
            raise SlotConflictError()

        return instance