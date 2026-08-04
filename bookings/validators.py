from datetime import datetime, timedelta
from django.utils import timezone
from .models import Appointment, WorkingHours
from rest_framework.exceptions import ValidationError as DRFValidationError

# Availability is computed via exact start_time match rather than range-overlap
# checks, consistent with the fixed 30-minute grid design — see README trade-offs.

SLOT_MINUTES = 30

class SlotConflictError(Exception):
    """Raised when a slot conflicts with the DB's partial unique constraint,
    whether caught via full_clean()'s validate_unique() or a raw IntegrityError."""
    pass


def generate_slots_for_doctor(doctor, date):
    weekday = date.weekday()
    # .first() is safe here: (doctor, weekday) is enforced unique at the DB level
    # via WorkingHours.Meta.constraints, so at most one row can ever match.
    hours = WorkingHours.objects.filter(doctor=doctor, weekday=weekday).first()

    if not hours:
        return []

    slots = []
    current = datetime.combine(date, hours.start_time)
    end_of_day = datetime.combine(date, hours.end_time)
    current = timezone.make_aware(current)
    end_of_day = timezone.make_aware(end_of_day)

    while current + timedelta(minutes=SLOT_MINUTES) <= end_of_day:
        slot_end = current + timedelta(minutes=SLOT_MINUTES)
        slots.append((current, slot_end))
        current = slot_end

    return slots


def get_available_slots(doctor, date):
    all_slots = generate_slots_for_doctor(doctor, date)

    booked_starts = set(
        Appointment.objects.filter(
            doctor=doctor,
            status=Appointment.Status.BOOKED,
            start_time__date=date,
        ).values_list("start_time", flat=True)
    )

    return [(start, end) for start, end in all_slots if start not in booked_starts]


def validate_slot_is_bookable(doctor, start_time):
    now = timezone.now()

    if start_time < now:
        raise DRFValidationError({"start_time": "Cannot book an appointment in the past."})

    date = start_time.date()
    valid_slots = generate_slots_for_doctor(doctor, date)
    valid_starts = {slot_start: slot_end for slot_start, slot_end in valid_slots}

    if start_time not in valid_starts:
        raise DRFValidationError({
            "start_time": "This time is not a valid slot for this doctor "
                           "(outside working hours or not aligned to a 30-minute boundary)."
        })

    return valid_starts[start_time]