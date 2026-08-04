from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Doctor, Appointment
from .validators import get_available_slots, SlotConflictError
from .serializers import (
    AvailableSlotSerializer,
    AvailabilityQuerySerializer,
    AppointmentCreateSerializer,
    AppointmentCancelSerializer,
    AppointmentRescheduleSerializer,
    AppointmentResponseSerializer,
)

from django.db import IntegrityError


class DoctorAvailabilityView(APIView):
    def get(self, request, doctor_id):
        doctor = get_object_or_404(Doctor, id=doctor_id)

        query_serializer = AvailabilityQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return Response(query_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        date = query_serializer.validated_data["date"]
        slots = get_available_slots(doctor, date)
        data = [{"start_time": s, "end_time": e} for s, e in slots]
        serializer = AvailableSlotSerializer(data, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


class AppointmentCreateView(APIView):
    def post(self, request):
        serializer = AppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            appointment = serializer.save()
        except IntegrityError as e:
            # Raw DB-level IntegrityError has no structured error_dict/code to
            # inspect (unlike the DjangoValidationError path used in cancel/
            # reschedule), so checking the constraint name in the message is
            # the practical option here — this is the genuine race-condition
            # path where two requests both passed app-level validation.
            if "unique_booked_doctor_slot" in str(e):
                return Response(
                    {"start_time": "This slot was just booked by someone else. Please choose another."},
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        return Response(AppointmentResponseSerializer(appointment).data, status=status.HTTP_201_CREATED)


class AppointmentCancelView(APIView):
    def patch(self, request, appointment_id):
        appointment = get_object_or_404(Appointment, id=appointment_id)

        serializer = AppointmentCancelSerializer(appointment, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(AppointmentResponseSerializer(appointment).data, status=status.HTTP_200_OK)


class AppointmentRescheduleView(APIView):
    def patch(self, request, appointment_id):
        appointment = get_object_or_404(Appointment, id=appointment_id)

        serializer = AppointmentRescheduleSerializer(appointment, data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save()
        except SlotConflictError:
            return Response(
                {"start_time": "This slot was just booked by someone else. Please choose another."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(AppointmentResponseSerializer(appointment).data, status=status.HTTP_200_OK)