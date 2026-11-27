"""
Casos de uso de escrita. Toda regra de negócio e todo controle transacional de
reservas fica aqui; as views apenas validam formato e chamam estas funções.
"""

from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from reservations import selectors
from reservations.exceptions import (
    InvalidReservationPeriod,
    ReservationConflict,
    ReservationNotFound,
    ResourceAlreadyExists,
    ResourceNotFound,
)
from reservations.models import Reservation, ReservationStatus, ReservationStatusHistory, Resource
from reservations.state_machine import ensure_transition_allowed


def create_resource(*, name: str, description: str = "") -> Resource:
    name = " ".join(name.split())
    try:
        # Savepoint próprio: o IntegrityError não contamina uma transação externa.
        with transaction.atomic():
            return Resource.objects.create(name=name, description=description)
    except IntegrityError as exc:
        # A constraint do banco é a fonte da verdade (checar antes com SELECT
        # teria condição de corrida). Aqui apenas traduzimos o erro.
        if Resource.objects.filter(normalized_name=Resource.normalize_name(name)).exists():
            raise ResourceAlreadyExists(details={"name": name}) from exc
        raise


def create_reservation(
    *,
    resource_id: int,
    customer_name: str,
    start_at: datetime,
    end_at: datetime,
    idempotency_key: str = "",
    request_id: str = "",
    now: datetime | None = None,
) -> Reservation:
    _validate_period(start_at=start_at, end_at=end_at, now=now or timezone.now())

    with transaction.atomic():
        # Lock pessimista na linha do recurso: serializa as criações de reserva
        # para o MESMO recurso (recursos diferentes não se bloqueiam). Assim a
        # checagem de sobreposição abaixo e o INSERT ficam atômicos.
        # Portável: SELECT ... FOR UPDATE funciona igual em PostgreSQL e InnoDB,
        # ao contrário da ExclusionConstraint, que só existe no PostgreSQL.
        resource = Resource.objects.select_for_update().filter(pk=resource_id).first()
        if resource is None:
            raise ResourceNotFound(details={"resource_id": resource_id})

        conflicting = selectors.overlapping_reservations(
            resource_id=resource.pk, start_at=start_at, end_at=end_at
        ).first()
        if conflicting is not None:
            raise ReservationConflict(
                details={
                    "conflicting_reservation_id": conflicting.pk,
                    "conflicting_start_at": conflicting.start_at.isoformat(),
                    "conflicting_end_at": conflicting.end_at.isoformat(),
                }
            )

        reservation = Reservation.objects.create(
            resource=resource,
            customer_name=customer_name.strip(),
            start_at=start_at,
            end_at=end_at,
            status=ReservationStatus.PENDENTE,
        )
        ReservationStatusHistory.objects.create(
            reservation=reservation,
            from_status=None,
            to_status=reservation.status,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
    return reservation


def transition_reservation(
    *,
    reservation_id: int,
    to_status: str,
    idempotency_key: str = "",
    request_id: str = "",
) -> Reservation:
    with transaction.atomic():
        # Lock na reserva: duas transições simultâneas (ex.: confirmar e
        # cancelar) não podem ler o mesmo estado antigo e as duas "vencerem".
        reservation = Reservation.objects.select_for_update().filter(pk=reservation_id).first()
        if reservation is None:
            raise ReservationNotFound(details={"reservation_id": reservation_id})

        from_status = reservation.status
        ensure_transition_allowed(from_status, to_status)

        reservation.status = to_status
        reservation.save(update_fields=["status", "updated_at"])
        ReservationStatusHistory.objects.create(
            reservation=reservation,
            from_status=from_status,
            to_status=to_status,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
    return reservation


def _validate_period(*, start_at: datetime, end_at: datetime, now: datetime) -> None:
    if end_at <= start_at:
        raise InvalidReservationPeriod(
            "O fim da reserva deve ser posterior ao início.",
            details={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        )
    if start_at < now:
        raise InvalidReservationPeriod(
            "Não é possível criar reservas no passado.",
            details={"start_at": start_at.isoformat()},
        )
