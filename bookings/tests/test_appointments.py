from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from bookings.models import Doctor, Patient, WorkingHours, Appointment


class AppointmentCreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name="Dr. Wanjiru", specialty="General Practice")
        self.patient = Patient.objects.create(name="Jane Doe", phone="0712345678")

        for weekday in range(5):  # Mon-Fri
            WorkingHours.objects.create(
                doctor=self.doctor,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )

        self.url = reverse("appointment-create")

    def _future_monday_at(self, hour, minute=0):
        """Helper: returns an aware datetime for a future Monday at the given time."""
        today = timezone.localdate()
        days_ahead = (0 - today.weekday()) % 7 or 7  # next Monday, always in the future
        target_date = today + timedelta(days=days_ahead)
        naive = timezone.datetime.combine(target_date, time(hour, minute))
        return timezone.make_aware(naive)

    def test_successful_booking_returns_201(self):
        start_time = self._future_monday_at(9, 0)
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(response.data["status"], "booked")

        expected_end_time = start_time + timedelta(minutes=30)
        self.assertEqual(response.data["end_time"], expected_end_time.isoformat())

    def test_booking_in_the_past_returns_400(self):
        past_time = timezone.now() - timedelta(days=1)
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": past_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)

    def test_booking_outside_working_hours_returns_400(self):
        start_time = self._future_monday_at(20, 0)  # 8pm, outside 9-5
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)

    def test_booking_exactly_at_working_hours_end_returns_400(self):
        # Working hours end at 17:00. A slot starting at 17:00 would end at
        # 17:30, past closing, so generate_slots_for_doctor never produces it.
        start_time = self._future_monday_at(17, 0)
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)

    def test_booking_misaligned_to_slot_boundary_returns_400(self):
        start_time = self._future_monday_at(9, 15)  # not on a 30-min boundary
        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)
        self.assertTrue(
            any("valid slot" in str(err).lower() for err in response.data["start_time"])
        )

    def test_booking_on_non_working_day_returns_400(self):
        today = timezone.localdate()
        days_ahead = (5 - today.weekday()) % 7 or 7  # next Saturday
        saturday = today + timedelta(days=days_ahead)
        naive = timezone.datetime.combine(saturday, time(9, 0))
        start_time = timezone.make_aware(naive)

        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_double_booking_same_slot_returns_409(self):
        start_time = self._future_monday_at(10, 0)
        payload = {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        }

        first_response = self.client.post(self.url, payload)
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_patient = Patient.objects.create(name="John Smith", phone="0798765432")
        payload["patient"] = second_patient.id
        second_response = self.client.post(self.url, payload)

        self.assertEqual(second_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_rebooking_a_cancelled_slot_succeeds(self):
        start_time = self._future_monday_at(11, 0)
        Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=30),
            status=Appointment.Status.CANCELLED,
            cancellation_reason="Patient request",
        )

        response = self.client.post(self.url, {
            "doctor": self.doctor.id,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Appointment.objects.filter(doctor=self.doctor, start_time=start_time).count(), 2
        )

    def test_missing_required_fields_returns_400(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_doctor_returns_400(self):
        start_time = self._future_monday_at(9, 0)
        response = self.client.post(self.url, {
            "doctor": 9999,
            "patient": self.patient.id,
            "start_time": start_time.isoformat(),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)