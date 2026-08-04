from datetime import time

from django.core.management.base import BaseCommand
from bookings.models import Doctor, WorkingHours, Patient


class Command(BaseCommand):
    help = "Seeds demo doctors, working hours, and patients for manual API testing."

    def handle(self, *args, **options):
        doctors_data = [
            {"name": "Dr. Wanjiru", "specialty": "General Practice"},
            {"name": "Dr. Otieno", "specialty": "Pediatrics"},
            {"name": "Dr. Kimani", "specialty": "Dermatology"},
            {"name": "Dr. Achieng", "specialty": "Cardiology"},
            {"name": "Dr. Mwangi", "specialty": "Orthopedics"},
        ]

        for data in doctors_data:
            doctor, created = Doctor.objects.get_or_create(
                name=data["name"], defaults={"specialty": data["specialty"]}
            )
            status = "Created" if created else "Already exists"
            self.stdout.write(f"{status}: {doctor.name}")

            for weekday in range(5):  # Mon-Fri
                WorkingHours.objects.get_or_create(
                    doctor=doctor,
                    weekday=weekday,
                    defaults={"start_time": time(9, 0), "end_time": time(17, 0)},
                )

        patients_data = [
            {"name": "Jane Doe", "phone": "0712345678"},
            {"name": "John Smith", "phone": "0798765432"},
        ]

        for data in patients_data:
            patient, created = Patient.objects.get_or_create(
                name=data["name"], defaults={"phone": data["phone"]}
            )
            status = "Created" if created else "Already exists"
            self.stdout.write(f"{status}: {patient.name}")

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))