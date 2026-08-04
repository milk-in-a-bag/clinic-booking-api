from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from bookings.models import Doctor, Patient, WorkingHours, Appointment


class AppointmentRescheduleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name="Dr. Wanjiru", specialty="General Practice")
        self.patient = Patient.objects.create(name="Jane Doe", phone="0712345678")

        for weekday in range(5):
            WorkingHours.objects.create(
                doctor=self.doctor,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )

        self.original_start = self._future_monday_at(9, 0)
        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            start_time=self.original_start,
            end_time=self.original_start + timedelta(minutes=30),
            status=Appointment.Status.BOOKED,
        )

        self.url = reverse("appointment-reschedule", kwargs={"appointment_id": self.appointment.id})

    def _future_monday_at(self, hour, minute=0):
        today = timezone.localdate()
        days_ahead = (0 - today.weekday()) % 7 or 7
        target_date = today + timedelta(days=days_ahead)
        naive = timezone.datetime.combine(target_date, time(hour, minute))
        return timezone.make_aware(naive)

    def test_successful_reschedule_returns_200(self):
        new_start = self._future_monday_at(11, 0)
        response = self.client.patch(self.url, {"start_time": new_start.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.start_time, new_start)
        self.assertEqual(self.appointment.status, Appointment.Status.BOOKED)

    def test_original_slot_becomes_available_after_reschedule(self):
        new_start = self._future_monday_at(11, 0)
        self.client.patch(self.url, {"start_time": new_start.isoformat()})

        # Book a new appointment into the now-vacated original slot
        create_url = reverse("appointment-create")
        second_patient = Patient.objects.create(name="John Smith", phone="0798765432")
        response = self.client.post(create_url, {
            "doctor": self.doctor.id,
            "patient": second_patient.id,
            "start_time": self.original_start.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_reschedule_to_taken_slot_returns_409(self):
        other_patient = Patient.objects.create(name="John Smith", phone="0798765432")
        taken_start = self._future_monday_at(14, 0)
        Appointment.objects.create(
            doctor=self.doctor,
            patient=other_patient,
            start_time=taken_start,
            end_time=taken_start + timedelta(minutes=30),
            status=Appointment.Status.BOOKED,
        )

        response = self.client.patch(self.url, {"start_time": taken_start.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.start_time, self.original_start)  # unchanged

    def test_reschedule_to_invalid_slot_returns_400(self):
        bad_time = self._future_monday_at(9, 15)  # not on a 30-min boundary
        response = self.client.patch(self.url, {"start_time": bad_time.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.start_time, self.original_start)

    def test_reschedule_to_past_time_returns_400(self):
        past_time = timezone.now() - timedelta(days=1)
        response = self.client.patch(self.url, {"start_time": past_time.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rescheduling_cancelled_appointment_returns_400(self):
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.cancellation_reason = "Patient request"
        self.appointment.save()

        new_start = self._future_monday_at(11, 0)
        response = self.client.patch(self.url, {"start_time": new_start.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_rescheduling_nonexistent_appointment_returns_404(self):
        url = reverse("appointment-reschedule", kwargs={"appointment_id": 9999})
        response = self.client.patch(url, {"start_time": self._future_monday_at(11, 0).isoformat()})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_start_time_returns_400(self):
        response = self.client.patch(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)