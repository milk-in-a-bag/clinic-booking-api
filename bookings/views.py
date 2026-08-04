from datetime import datetime

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Doctor
from .validators import get_available_slots
from .serializers import AvailableSlotSerializer

# Create your views here.

class DoctorAvailabilityView(APIView):
    def get(self, request, doctor_id):
        doctor = get_object_or_404(Doctor, id=doctor_id)

        date_param = request.query_params.get("date")
        if not date_param:
            return Response(
                {"error": "Query parameter 'date' is required (format: YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slots = get_available_slots(doctor, date)
        data = [{"start_time": s, "end_time": e} for s, e in slots]
        serializer = AvailableSlotSerializer(data, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)