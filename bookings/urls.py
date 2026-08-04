from django.urls import path
from .views import DoctorAvailabilityView, AppointmentCreateView

urlpatterns = [
    path("doctors/<int:doctor_id>/availability/", DoctorAvailabilityView.as_view(), name="doctor-availability"),
    path("appointments/", AppointmentCreateView.as_view(), name="appointment-create"),
]