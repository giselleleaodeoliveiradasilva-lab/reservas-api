from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from reservations import services
from reservations.exceptions import (
    InvalidReservationPeriod,
    InvalidStatusTransition,
    ReservationConflict,
    ReservationNotFound,
    ResourceAlreadyExists,
    ResourceNotFound,
)
from reservations.models import Reservation, ReservationStatus as S, ReservationStatusHistory, Resource

pytestmark = pytest.mark.django_db


class TestCreateResource:
    def test_creates_resource_with_collapsed_whitespace(self):
        resource = services.create_resource(name="  Sala   Verde ")
        assert resource.name == "Sala Verde"
        assert resource.normalized_name == "sala verde"

    @pytest.mark.parametrize("duplicate", ["Sala Azul", "sala azul", "  SALA   AZUL "])
    def test_duplicate_name_is_rejected_regardless_of_case_and_spaces(self, resource, duplicate):
        with pytest.raises(ResourceAlreadyExists):
            services.create_resource(name=duplicate)
        assert Resource.objects.count() == 1


class TestCreateReservation:
    def test_creates_pending_reservation_and_records_history(self, resource, base_time):
        reservation = services.create_reservation(
            resource_id=resource.pk,
            customer_name=" Ana ",
            start_at=base_time,
            end_at=base_time + timedelta(hours=1),
            idempotency_key="k-1",
            request_id="req-1",
        )

        assert reservation.status == S.PENDENTE
        assert reservation.customer_name == "Ana"
        history = list(ReservationStatusHistory.objects.filter(reservation=reservation))
        assert len(history) == 1
        assert (history[0].from_status, history[0].to_status) == (None, S.PENDENTE)
        assert (history[0].idempotency_key, history[0].request_id) == ("k-1", "req-1")

    def test_end_must_be_after_start(self, resource, base_time):
        with pytest.raises(InvalidReservationPeriod):
            services.create_reservation(
                resource_id=resource.pk, customer_name="Ana", start_at=base_time, end_at=base_time
            )

    def test_cannot_book_in_the_past(self, resource):
        start = timezone.now() - timedelta(hours=1)
        with pytest.raises(InvalidReservationPeriod):
            services.create_reservation(
                resource_id=resource.pk, customer_name="Ana", start_at=start, end_at=start + timedelta(hours=2)
            )

    def test_unknown_resource(self, db, base_time):
        with pytest.raises(ResourceNotFound):
            services.create_reservation(
                resource_id=999_999, customer_name="Ana", start_at=base_time, end_at=base_time + timedelta(hours=1)
            )

    @pytest.mark.parametrize(
        ("offset_h", "duration_h"),
        [
            (0, 2),  # mesmo intervalo
            (1, 1),  # começa no meio
            (-1, 2),  # termina no meio
            (-1, 4),  # engloba
        ],
    )
    def test_overlapping_active_reservation_is_rejected(self, make_reservation, offset_h, duration_h):
        existing = make_reservation(start_offset_h=0, duration_h=2)
        with pytest.raises(ReservationConflict) as exc_info:
            make_reservation(start_offset_h=offset_h, duration_h=duration_h)
        assert exc_info.value.details["conflicting_reservation_id"] == existing.pk
        assert Reservation.objects.count() == 1

    def test_adjacent_reservations_do_not_conflict(self, make_reservation):
        make_reservation(start_offset_h=0, duration_h=1)
        make_reservation(start_offset_h=1, duration_h=1)  # começa exatamente quando a outra termina
        make_reservation(start_offset_h=-1, duration_h=1)  # termina exatamente quando a primeira começa
        assert Reservation.objects.count() == 3

    @pytest.mark.parametrize("final_path", [[S.CANCELADA], [S.CONFIRMADA, S.CONCLUIDA]])
    def test_inactive_reservation_frees_the_slot(self, make_reservation, final_path):
        existing = make_reservation()
        for to_status in final_path:
            services.transition_reservation(reservation_id=existing.pk, to_status=to_status)
        make_reservation()  # não levanta
        assert Reservation.objects.count() == 2

    def test_other_resource_is_independent(self, make_reservation):
        other = services.create_resource(name="Sala Vermelha")
        make_reservation()
        make_reservation(resource_id=other.pk)
        assert Reservation.objects.count() == 2

    def test_database_check_constraint_enforces_period(self, resource, base_time):
        # Mesmo escrevendo direto no ORM (sem service), o banco recusa o dado.
        with pytest.raises(IntegrityError), transaction.atomic():
            Reservation.objects.create(
                resource=resource, customer_name="X", start_at=base_time, end_at=base_time - timedelta(hours=1)
            )


class TestTransitionReservation:
    def test_valid_transition_updates_status_and_history(self, make_reservation):
        reservation = make_reservation()
        services.transition_reservation(
            reservation_id=reservation.pk, to_status=S.CONFIRMADA, idempotency_key="k-2", request_id="r-2"
        )
        reservation.refresh_from_db()
        assert reservation.status == S.CONFIRMADA

        last = ReservationStatusHistory.objects.filter(reservation=reservation).last()
        assert (last.from_status, last.to_status) == (S.PENDENTE, S.CONFIRMADA)
        assert (last.idempotency_key, last.request_id) == ("k-2", "r-2")

    def test_invalid_transition_changes_nothing(self, make_reservation):
        reservation = make_reservation()
        with pytest.raises(InvalidStatusTransition):
            services.transition_reservation(reservation_id=reservation.pk, to_status=S.CONCLUIDA)

        reservation.refresh_from_db()
        assert reservation.status == S.PENDENTE
        assert ReservationStatusHistory.objects.filter(reservation=reservation).count() == 1

    def test_full_lifecycle_history_is_ordered(self, make_reservation):
        reservation = make_reservation()
        services.transition_reservation(reservation_id=reservation.pk, to_status=S.CONFIRMADA)
        services.transition_reservation(reservation_id=reservation.pk, to_status=S.CONCLUIDA)

        steps = list(
            ReservationStatusHistory.objects.filter(reservation=reservation).values_list("from_status", "to_status")
        )
        assert steps == [(None, S.PENDENTE), (S.PENDENTE, S.CONFIRMADA), (S.CONFIRMADA, S.CONCLUIDA)]

    def test_unknown_reservation(self, db):
        with pytest.raises(ReservationNotFound):
            services.transition_reservation(reservation_id=999_999, to_status=S.CONFIRMADA)
