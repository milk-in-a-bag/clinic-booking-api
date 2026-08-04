from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from bookings.models import Doctor, Patient, WorkingHours, Appointment


class PatientAppointmentsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name="Dr. Wanjiru", specialty="General Practice")
        self.patient = Patient.objects.create(name="Jane Doe", phone="0712345678")
        self.url = reverse("patient-appointments", kwargs={"patient_id": self.patient.id})

    def _create_appointment(self, start_time, status_=Appointment.Status.BOOKED):
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=30),
            status=status_,
            cancellation_reason="N/A" if status_ == Appointment.Status.CANCELLED else None,
        )

    def test_returns_upcoming_booked_appointments_sorted_by_date(self):
        later = self._create_appointment(timezone.now() + timedelta(days=5))
        sooner = self._create_appointment(timezone.now() + timedelta(days=2))

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["id"], sooner.id)
        self.assertEqual(response.data[1]["id"], later.id)

    def test_excludes_past_appointments(self):
        self._create_appointment(timezone.now() - timedelta(days=2))

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_excludes_cancelled_appointments(self):
        self._create_appointment(
            timezone.now() + timedelta(days=2), status_=Appointment.Status.CANCELLED
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_only_returns_appointments_for_the_requested_patient(self):
        other_patient = Patient.objects.create(name="John Smith", phone="0798765432")
        Appointment.objects.create(
            doctor=self.doctor,
            patient=other_patient,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, minutes=30),
            status=Appointment.Status.BOOKED,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_nonexistent_patient_returns_404(self):
        url = reverse("patient-appointments", kwargs={"patient_id": 9999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BookingBufferTests(TestCase):
    """Covers the bonus rule: prevent bookings within 1 hour of now."""

    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name="Dr. Wanjiru", specialty="General Practice")
        self.patient = Patient.objects.create(name="Jane Doe", phone="0712345678")

        for weekday in range(7):
            WorkingHours.objects.create(
                doctor=self.doctor, weekday=weekday, start_time=time(0, 0), end_time=time(23, 30)
            )

        self.url = reverse("appointment-create")

    def _next_slot_boundary(self, minutes_from_now):
        target = timezone.now() + timedelta(minutes=minutes_from_now)
        rounded_minute = 0 if target.minute < 30 else 30
        return target.replace(minute=rounded_minute, second=0, microsecond=0)

    def test_booking_within_1_hour_returns_400(self):
        start_time = self._next_slot_boundary(30)  # ~30 min from now
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)

    def test_booking_after_1_hour_buffer_succeeds(self):
        start_time = self._next_slot_boundary(120)  # 2 hours from now, safely past the buffer
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)