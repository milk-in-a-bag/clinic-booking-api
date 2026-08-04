from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from bookings.models import Doctor, Patient, WorkingHours, Appointment


class AppointmentCancelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name="Dr. Wanjiru", specialty="General Practice")
        self.patient = Patient.objects.create(name="Jane Doe", phone="0712345678")

        raw_start = timezone.now() + timedelta(days=1)
        # Round down to the nearest 30-minute boundary so this lines up with
        # what generate_slots_for_doctor would actually produce.
        minute = 0 if raw_start.minute < 30 else 30
        start_time = raw_start.replace(minute=minute, second=0, microsecond=0)

        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=30),
            status=Appointment.Status.BOOKED,
        )

        self.url = reverse("appointment-cancel", kwargs={"appointment_id": self.appointment.id})

    def test_successful_cancel_returns_200(self):
        response = self.client.patch(self.url, {"cancellation_reason": "Patient request"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(self.appointment.cancellation_reason, "Patient request")

    def test_cancel_without_reason_returns_400(self):
        response = self.client.patch(self.url, {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cancellation_reason", response.data)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.BOOKED)

    def test_cancel_with_blank_reason_returns_400(self):
        response = self.client.patch(self.url, {"cancellation_reason": ""})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelling_already_cancelled_appointment_returns_400(self):
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.cancellation_reason = "Original reason"
        self.appointment.save()

        response = self.client.patch(self.url, {"cancellation_reason": "Trying again"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_cancelling_nonexistent_appointment_returns_404(self):
        url = reverse("appointment-cancel", kwargs={"appointment_id": 9999})
        response = self.client.patch(url, {"cancellation_reason": "N/A"})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancelled_slot_becomes_rebookable(self):
        self.client.patch(self.url, {"cancellation_reason": "Patient request"})

        for weekday in range(7):
            WorkingHours.objects.get_or_create(
                doctor=self.doctor,
                weekday=weekday,
                defaults={"start_time": time(0, 0), "end_time": time(23, 30)},
            )

        availability_url = reverse("doctor-availability", kwargs={"doctor_id": self.doctor.id})
        response = self.client.get(availability_url, {"date": self.appointment.start_time.date().isoformat()})

        slot_start_datetimes = [
            datetime.fromisoformat(s["start_time"]) for s in response.data
        ]
        self.assertIn(self.appointment.start_time, slot_start_datetimes)