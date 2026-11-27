from datetime import timedelta

import pytest

from core.idempotency.models import IdempotencyKey
from reservations import services
from reservations.models import Reservation, ReservationStatus as S, ReservationStatusHistory
from reservations.tests.integration.test_resources_api import assert_error

pytestmark = pytest.mark.django_db

URL = "/api/v1/reservations/"


def iso(dt):
    return dt.isoformat()


@pytest.fixture
def payload(resource, base_time):
    return {
        "resource_id": resource.pk,
        "customer_name": "Ana",
        "start_at": iso(base_time),
        "end_at": iso(base_time + timedelta(hours=1)),
    }


def post_reservation(client, payload, key):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
    return client.post(URL, payload, format="json", **headers)


def post_transition(client, reservation_id, to_status, key):
    return client.post(
        f"{URL}{reservation_id}/transitions/",
        {"to_status": to_status},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


# --- Criação -------------------------------------------------------------------

class TestCreateReservation:
    def test_creates_reservation(self, api_client, payload, idem_key):
        response = post_reservation(api_client, payload, idem_key())

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == S.PENDENTE
        assert body["resource_id"] == payload["resource_id"]
        assert body["allowed_transitions"] == [S.CANCELADA, S.CONFIRMADA]
        assert "Idempotent-Replayed" not in response

    def test_idempotency_key_is_required(self, api_client, payload):
        response = post_reservation(api_client, payload, key=None)
        assert_error(response, 400, "idempotency_key_required")
        assert Reservation.objects.count() == 0

    def test_invalid_idempotency_key(self, api_client, payload):
        response = post_reservation(api_client, payload, key="chave com espaço")
        assert_error(response, 400, "idempotency_key_invalid")

    def test_replay_returns_same_response_and_creates_nothing_new(self, api_client, payload, idem_key):
        key = idem_key()
        first = post_reservation(api_client, payload, key)
        second = post_reservation(api_client, payload, key)

        assert first.status_code == second.status_code == 201
        assert second.json() == first.json()
        assert second["Idempotent-Replayed"] == "true"
        assert Reservation.objects.count() == 1
        assert ReservationStatusHistory.objects.count() == 1

    def test_same_key_with_different_payload_returns_422(self, api_client, payload, idem_key):
        key = idem_key()
        post_reservation(api_client, payload, key)

        response = post_reservation(api_client, {**payload, "customer_name": "Bruno"}, key)

        assert_error(response, 422, "idempotency_key_reused")
        assert Reservation.objects.count() == 1

    def test_overlap_returns_409(self, api_client, payload, idem_key):
        first = post_reservation(api_client, payload, idem_key())

        response = post_reservation(api_client, {**payload, "customer_name": "Bruno"}, idem_key())

        error = assert_error(response, 409, "reservation_conflict")
        assert error["details"]["conflicting_reservation_id"] == first.json()["id"]

    def test_failed_request_does_not_consume_key(self, api_client, payload, base_time, idem_key):
        key = idem_key()
        bad = {**payload, "end_at": iso(base_time - timedelta(hours=1))}
        assert_error(post_reservation(api_client, bad, key), 400, "invalid_reservation_period")
        assert not IdempotencyKey.objects.filter(key=key).exists()

        assert post_reservation(api_client, payload, key).status_code == 201

    def test_unknown_resource_returns_404(self, api_client, payload, idem_key):
        response = post_reservation(api_client, {**payload, "resource_id": 999999}, idem_key())
        assert_error(response, 404, "resource_not_found")

    def test_missing_fields_returns_400(self, api_client, idem_key):
        response = post_reservation(api_client, {}, idem_key())
        error = assert_error(response, 400, "validation_error")
        assert {"resource_id", "customer_name", "start_at", "end_at"} <= set(error["details"])


# --- Consulta e listagem -------------------------------------------------------

class TestReadReservations:
    def test_get_reservation(self, api_client, make_reservation):
        reservation = make_reservation()
        response = api_client.get(f"{URL}{reservation.pk}/")
        assert response.status_code == 200
        assert response.json()["id"] == reservation.pk

    def test_get_unknown_reservation(self, api_client, db):
        assert_error(api_client.get(f"{URL}999999/"), 404, "reservation_not_found")

    def test_list_is_paginated_and_ordered_by_start(self, api_client, make_reservation):
        later = make_reservation(start_offset_h=5)
        earlier = make_reservation(start_offset_h=0)
        make_reservation(start_offset_h=10)

        response = api_client.get(URL, {"page_size": 2})

        body = response.json()
        assert body["count"] == 3
        assert [r["id"] for r in body["results"]] == [earlier.pk, later.pk]
        assert body["next"] is not None

    def test_filter_by_status_and_resource(self, api_client, make_reservation):
        other = services.create_resource(name="Sala Vermelha")
        pending = make_reservation(start_offset_h=0)
        confirmed = make_reservation(start_offset_h=2)
        services.transition_reservation(reservation_id=confirmed.pk, to_status=S.CONFIRMADA)
        in_other = make_reservation(resource_id=other.pk)

        by_status = api_client.get(URL, {"status": S.CONFIRMADA}).json()
        assert [r["id"] for r in by_status["results"]] == [confirmed.pk]

        by_resource = api_client.get(URL, {"resource": other.pk}).json()
        assert [r["id"] for r in by_resource["results"]] == [in_other.pk]

        both = api_client.get(URL, {"resource": pending.resource_id, "status": S.PENDENTE}).json()
        assert [r["id"] for r in both["results"]] == [pending.pk]

    def test_filter_by_period(self, api_client, make_reservation, base_time):
        make_reservation(start_offset_h=0)
        inside = make_reservation(start_offset_h=3)
        make_reservation(start_offset_h=6)

        response = api_client.get(
            URL,
            {"start_from": iso(base_time + timedelta(hours=2)), "start_to": iso(base_time + timedelta(hours=5))},
        )

        assert [r["id"] for r in response.json()["results"]] == [inside.pk]

    def test_invalid_filter_returns_400(self, api_client, db):
        response = api_client.get(URL, {"status": "INEXISTENTE"})
        error = assert_error(response, 400, "validation_error")
        assert "status" in error["details"]

    def test_page_out_of_range_returns_404(self, api_client, db):
        assert_error(api_client.get(URL, {"page": 99}), 404, "not_found")


# --- Transições ------------------------------------------------------------------

class TestTransitions:
    def test_confirm_reservation(self, api_client, make_reservation, idem_key):
        reservation = make_reservation()
        response = post_transition(api_client, reservation.pk, S.CONFIRMADA, idem_key())

        assert response.status_code == 200
        assert response.json()["status"] == S.CONFIRMADA
        assert response.json()["allowed_transitions"] == [S.CANCELADA, S.CONCLUIDA]

    def test_invalid_transition_returns_409(self, api_client, make_reservation, idem_key):
        reservation = make_reservation()

        response = post_transition(api_client, reservation.pk, S.CONCLUIDA, idem_key())

        error = assert_error(response, 409, "invalid_status_transition")
        assert error["details"] == {
            "from_status": S.PENDENTE,
            "to_status": S.CONCLUIDA,
            "allowed_to_status": [S.CANCELADA, S.CONFIRMADA],
        }

    def test_terminal_state_cannot_change(self, api_client, make_reservation, idem_key):
        reservation = make_reservation()
        post_transition(api_client, reservation.pk, S.CANCELADA, idem_key())

        response = post_transition(api_client, reservation.pk, S.CONFIRMADA, idem_key())
        assert_error(response, 409, "invalid_status_transition")

    def test_unknown_status_returns_400(self, api_client, make_reservation, idem_key):
        reservation = make_reservation()
        response = post_transition(api_client, reservation.pk, "APROVADA", idem_key())
        assert_error(response, 400, "validation_error")

    def test_transition_requires_idempotency_key(self, api_client, make_reservation):
        reservation = make_reservation()
        response = api_client.post(f"{URL}{reservation.pk}/transitions/", {"to_status": S.CONFIRMADA}, format="json")
        assert_error(response, 400, "idempotency_key_required")

    def test_transition_replay_is_not_reapplied(self, api_client, make_reservation, idem_key):
        """Reenviar "cancelar" com a mesma chave devolve o sucesso original, não 409."""
        reservation = make_reservation()
        key = idem_key()

        first = post_transition(api_client, reservation.pk, S.CANCELADA, key)
        second = post_transition(api_client, reservation.pk, S.CANCELADA, key)

        assert first.status_code == second.status_code == 200
        assert second.json() == first.json()
        assert second["Idempotent-Replayed"] == "true"
        assert ReservationStatusHistory.objects.filter(reservation=reservation).count() == 2

    def test_reusing_key_on_another_reservation_returns_422(self, api_client, make_reservation, idem_key):
        first = make_reservation(start_offset_h=0)
        second = make_reservation(start_offset_h=2)
        key = idem_key()

        post_transition(api_client, first.pk, S.CONFIRMADA, key)
        response = post_transition(api_client, second.pk, S.CONFIRMADA, key)

        assert_error(response, 422, "idempotency_key_reused")

    def test_unknown_reservation_returns_404(self, api_client, db, idem_key):
        assert_error(post_transition(api_client, 999999, S.CONFIRMADA, idem_key()), 404, "reservation_not_found")


# --- Histórico e rastreabilidade ----------------------------------------------------

class TestHistoryAndTracing:
    def test_history_lists_all_state_changes(self, api_client, payload, idem_key):
        create_key, confirm_key = idem_key(), idem_key()
        reservation_id = post_reservation(api_client, payload, create_key).json()["id"]
        post_transition(api_client, reservation_id, S.CONFIRMADA, confirm_key)

        response = api_client.get(f"{URL}{reservation_id}/history/")

        assert response.status_code == 200
        results = response.json()["results"]
        assert [(h["from_status"], h["to_status"]) for h in results] == [
            (None, S.PENDENTE),
            (S.PENDENTE, S.CONFIRMADA),
        ]
        assert [h["idempotency_key"] for h in results] == [create_key, confirm_key]
        assert all(h["request_id"] and h["changed_at"] for h in results)

    def test_history_of_unknown_reservation_returns_404(self, api_client, db):
        assert_error(api_client.get(f"{URL}999999/history/"), 404, "reservation_not_found")

    def test_incoming_request_id_is_propagated_to_response_and_history(self, api_client, payload, idem_key):
        response = api_client.post(
            URL, payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_key(), HTTP_X_REQUEST_ID="req-abc-123"
        )

        assert response["X-Request-Id"] == "req-abc-123"
        history = ReservationStatusHistory.objects.get(reservation_id=response.json()["id"])
        assert history.request_id == "req-abc-123"

    def test_request_id_is_generated_when_missing_or_unsafe(self, api_client, db):
        generated = api_client.get(URL)
        assert len(generated["X-Request-Id"]) == 32

        unsafe = api_client.get(URL, HTTP_X_REQUEST_ID="x\nINJETADO")
        assert unsafe["X-Request-Id"] != "x\nINJETADO"
        assert len(unsafe["X-Request-Id"]) == 32
