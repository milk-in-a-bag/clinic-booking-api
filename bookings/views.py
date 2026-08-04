from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Doctor
from .validators import get_available_slots
from .serializers import AvailableSlotSerializer, AvailabilityQuerySerializer, AppointmentCreateSerializer

from django.db import IntegrityError

# Create your views here.

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
            if "unique_booked_doctor_slot" in str(e):
                return Response(
                    {"start_time": "This slot was just booked by someone else. Please choose another."},
                    status=status.HTTP_409_CONFLICT,
                )
            raise 

        return Response(AppointmentCreateSerializer(appointment).data, status=status.HTTP_201_CREATED)