"""
Testes de concorrência real: várias threads, cada uma com a própria conexão,
disputando o mesmo recurso. Usam transaction=True porque precisam de commits
de verdade (o modo padrão envolve o teste numa transação única).
"""

import threading
from datetime import timedelta

import pytest
from django.db import connection
from rest_framework.test import APIClient

from reservations import services
from reservations.models import Reservation, ReservationStatus as S, ReservationStatusHistory

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/reservations/"
THREADS = 5


def run_concurrently(fn, n=THREADS):
    """Dispara `fn` em n threads liberadas ao mesmo tempo; devolve os resultados."""
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def worker(i):
        try:
            barrier.wait()
            results[i] = fn(i)
        except Exception as exc:  # noqa: BLE001 - o teste inspeciona o erro
            results[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_only_one_of_many_concurrent_overlapping_reservations_wins(resource, base_time):
    def create(i):
        response = APIClient().post(
            URL,
            {
                "resource_id": resource.pk,
                "customer_name": f"Cliente {i}",
                "start_at": base_time.isoformat(),
                "end_at": (base_time + timedelta(hours=1)).isoformat(),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"conc-overlap-{i}",
        )
        return response.status_code

    statuses = run_concurrently(create)

    assert sorted(statuses) == [201] + [409] * (THREADS - 1), statuses
    assert Reservation.objects.count() == 1


def test_concurrent_retries_with_same_key_create_a_single_reservation(resource, base_time):
    payload = {
        "resource_id": resource.pk,
        "customer_name": "Ana",
        "start_at": base_time.isoformat(),
        "end_at": (base_time + timedelta(hours=1)).isoformat(),
    }

    def create(_):
        response = APIClient().post(URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="conc-same-key")
        return response.status_code, response.json()

    results = run_concurrently(create)

    assert all(r[0] == 201 for r in results), results
    assert len({r[1]["id"] for r in results}) == 1
    assert Reservation.objects.count() == 1
    assert ReservationStatusHistory.objects.count() == 1


def test_concurrent_conflicting_transitions_only_one_applies(resource, base_time):
    reservation = services.create_reservation(
        resource_id=resource.pk, customer_name="Ana", start_at=base_time, end_at=base_time + timedelta(hours=1)
    )
    services.transition_reservation(reservation_id=reservation.pk, to_status=S.CONFIRMADA)
    targets = [S.CONCLUIDA, S.CANCELADA]

    def transition(i):
        response = APIClient().post(
            f"{URL}{reservation.pk}/transitions/",
            {"to_status": targets[i % 2]},
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"conc-transition-{i}",
        )
        return response.status_code

    statuses = run_concurrently(transition, n=4)

    assert sorted(statuses) == [200, 409, 409, 409], statuses
    # Criação + confirmação + exatamente uma transição final.
    assert ReservationStatusHistory.objects.filter(reservation=reservation).count() == 3
