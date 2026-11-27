from django_filters import rest_framework as filters

from reservations.models import Reservation, ReservationStatus


class ReservationFilter(filters.FilterSet):
    resource = filters.NumberFilter(field_name="resource_id")
    status = filters.ChoiceFilter(choices=ReservationStatus.choices)
    # Janela pelo início da reserva: start_from <= start_at < start_to.
    start_from = filters.IsoDateTimeFilter(field_name="start_at", lookup_expr="gte")
    start_to = filters.IsoDateTimeFilter(field_name="start_at", lookup_expr="lt")

    class Meta:
        model = Reservation
        fields: list[str] = []
