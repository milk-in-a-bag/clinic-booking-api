from datetime import date, time

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from bookings.models import Doctor, WorkingHours


class DoctorAvailabilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name="Dr. Wanjiru", specialty="General Practice")
        # Monday-Friday, 9am-5pm
        for weekday in range(5):
            WorkingHours.objects.create(
                doctor=self.doctor,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )

    def test_returns_16_slots_for_a_working_day(self):
        # 2026-08-10 is a Monday
        url = reverse("doctor-availability", kwargs={"doctor_id": self.doctor.id})
        response = self.client.get(url, {"date": "2026-08-10"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 16)

    def test_first_slot_starts_at_9am_nairobi_time(self):
        url = reverse("doctor-availability", kwargs={"doctor_id": self.doctor.id})
        response = self.client.get(url, {"date": "2026-08-10"})

        first_slot_start = response.data[0]["start_time"]
        self.assertIn("09:00:00+03:00", first_slot_start)

    def test_returns_empty_list_for_non_working_day(self):
        # 2026-08-15 is a Saturday - no WorkingHours seeded for weekday 5
        url = reverse("doctor-availability", kwargs={"doctor_id": self.doctor.id})
        response = self.client.get(url, {"date": "2026-08-15"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_missing_date_param_returns_400(self):
        url = reverse("doctor-availability", kwargs={"doctor_id": self.doctor.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_date_format_returns_400(self):
        url = reverse("doctor-availability", kwargs={"doctor_id": self.doctor.id})
        response = self.client.get(url, {"date": "not-a-date"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_doctor_returns_404(self):
        url = reverse("doctor-availability", kwargs={"doctor_id": 9999})
        response = self.client.get(url, {"date": "2026-08-10"})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)