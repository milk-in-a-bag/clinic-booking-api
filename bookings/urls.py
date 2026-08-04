from django.urls import path
from .views import DoctorAvailabilityView, AppointmentCreateView, AppointmentCancelView, AppointmentRescheduleView

urlpatterns = [
    path("doctors/<int:doctor_id>/availability/", DoctorAvailabilityView.as_view(), name="doctor-availability"),
    path("appointments/", AppointmentCreateView.as_view(), name="appointment-create"),
    path("appointments/<int:appointment_id>/cancel/", AppointmentCancelView.as_view(), name="appointment-cancel"),
    path("appointments/<int:appointment_id>/reschedule/", AppointmentRescheduleView.as_view(), name="appointment-reschedule"),
]