"""
Views finas: validam a entrada, delegam ao service/selector e serializam a saída.
Erros (de domínio ou de validação) sobem como exceção e são formatados pelo
handler central em `core.exception_handler`.
"""

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from core.idempotency.http import idempotent_response, require_idempotency_key
from reservations import selectors, services
from reservations.api.filters import ReservationFilter
from reservations.api.serializers import (
    ReservationCreateSerializer,
    ReservationSerializer,
    ReservationStatusHistorySerializer,
    ReservationTransitionSerializer,
    ResourceCreateSerializer,
    ResourceSerializer,
)


class ResourceListCreateView(GenericAPIView):
    serializer_class = ResourceSerializer
    filter_backends: list = []

    def get_queryset(self):
        return selectors.resource_list()

    def get(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(ResourceSerializer(page, many=True).data)

    def post(self, request):
        serializer = ResourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = services.create_resource(**serializer.validated_data)
        return Response(ResourceSerializer(resource).data, status=status.HTTP_201_CREATED)


class ResourceDetailView(GenericAPIView):
    serializer_class = ResourceSerializer

    def get(self, request, pk: int):
        return Response(ResourceSerializer(selectors.resource_get(pk)).data)


class ReservationListCreateView(GenericAPIView):
    serializer_class = ReservationSerializer
    filterset_class = ReservationFilter

    def get_queryset(self):
        return selectors.reservation_list()

    def get(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(ReservationSerializer(page, many=True).data)

    def post(self, request):
        key = require_idempotency_key(request)
        serializer = ReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def operation():
            reservation = services.create_reservation(
                **data, idempotency_key=key, request_id=request.request_id
            )
            return status.HTTP_201_CREATED, ReservationSerializer(reservation).data

        return idempotent_response(key=key, scope="reservations.create", payload=data, operation=operation)


class ReservationDetailView(GenericAPIView):
    serializer_class = ReservationSerializer

    def get(self, request, pk: int):
        return Response(ReservationSerializer(selectors.reservation_get(pk)).data)


class ReservationTransitionView(GenericAPIView):
    serializer_class = ReservationTransitionSerializer

    def post(self, request, pk: int):
        key = require_idempotency_key(request)
        serializer = ReservationTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_status = serializer.validated_data["to_status"]

        def operation():
            reservation = services.transition_reservation(
                reservation_id=pk, to_status=to_status, idempotency_key=key, request_id=request.request_id
            )
            return status.HTTP_200_OK, ReservationSerializer(reservation).data

        # O id da reserva entra no hash: reusar a chave em outra reserva é 422.
        payload = {"reservation_id": pk, "to_status": to_status}
        return idempotent_response(key=key, scope="reservations.transition", payload=payload, operation=operation)


class ReservationHistoryView(GenericAPIView):
    serializer_class = ReservationStatusHistorySerializer
    filter_backends: list = []

    def get(self, request, pk: int):
        page = self.paginate_queryset(selectors.reservation_history(pk))
        return self.get_paginated_response(ReservationStatusHistorySerializer(page, many=True).data)
