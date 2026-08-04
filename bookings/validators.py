from datetime import datetime, timedelta
from django.utils import timezone
from .models import Appointment, WorkingHours

SLOT_MINUTES = 30


def generate_slots_for_doctor(doctor, date):
    weekday = date.weekday()
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