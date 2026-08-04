from django.urls import path
from .views import DoctorAvailabilityView, AppointmentCreateView, AppointmentCancelView, AppointmentRescheduleView, PatientAppointmentsView

urlpatterns = [
    path("doctors/<int:doctor_id>/availability/", DoctorAvailabilityView.as_view(), name="doctor-availability"),
    path("appointments/", AppointmentCreateView.as_view(), name="appointment-create"),
    path("appointments/<int:appointment_id>/cancel/", AppointmentCancelView.as_view(), name="appointment-cancel"),
    path("appointments/<int:appointment_id>/reschedule/", AppointmentRescheduleView.as_view(), name="appointment-reschedule"),
    path("patients/<int:patient_id>/appointments/", PatientAppointmentsView.as_view(), name="patient-appointments"),
]