"""Consultas de leitura. Nenhuma escrita acontece aqui."""

from datetime import datetime

from django.db.models import QuerySet

from reservations.exceptions import ReservationNotFound, ResourceNotFound
from reservations.models import Reservation, ReservationStatusHistory, Resource
from reservations.state_machine import ACTIVE_STATUSES


def resource_list() -> QuerySet[Resource]:
    return Resource.objects.order_by("id")


def resource_get(resource_id: int) -> Resource:
    resource = Resource.objects.filter(pk=resource_id).first()
    if resource is None:
        raise ResourceNotFound(details={"resource_id": resource_id})
    return resource


def reservation_list() -> QuerySet[Reservation]:
    # Ordenação total (start_at, id) para a paginação ser estável.
    return Reservation.objects.order_by("start_at", "id")


def reservation_get(reservation_id: int) -> Reservation:
    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None:
        raise ReservationNotFound(details={"reservation_id": reservation_id})
    return reservation


def reservation_history(reservation_id: int) -> QuerySet[ReservationStatusHistory]:
    if not Reservation.objects.filter(pk=reservation_id).exists():
        raise ReservationNotFound(details={"reservation_id": reservation_id})
    return ReservationStatusHistory.objects.filter(reservation_id=reservation_id).order_by("changed_at", "id")


def overlapping_reservations(*, resource_id: int, start_at: datetime, end_at: datetime) -> QuerySet[Reservation]:
    """Reservas ativas do recurso que se sobrepõem a [start_at, end_at)."""
    return Reservation.objects.filter(
        resource_id=resource_id,
        status__in=ACTIVE_STATUSES,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).order_by("start_at", "id")
