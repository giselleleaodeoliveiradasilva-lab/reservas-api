from datetime import timedelta
from itertools import count

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from reservations import services

_key_seq = count(1)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def base_time():
    """Um instante futuro "redondo", para montar intervalos legíveis nos testes."""
    return (timezone.now() + timedelta(days=7)).replace(hour=10, minute=0, second=0, microsecond=0)


@pytest.fixture
def resource(db):
    return services.create_resource(name="Sala Azul", description="Sala de reunião, 8 lugares")


@pytest.fixture
def make_reservation(resource, base_time):
    def _make(start_offset_h: int = 0, duration_h: int = 1, **kwargs):
        start = base_time + timedelta(hours=start_offset_h)
        params = {
            "resource_id": resource.pk,
            "customer_name": "Ana",
            "start_at": start,
            "end_at": start + timedelta(hours=duration_h),
        }
        params.update(kwargs)
        return services.create_reservation(**params)

    return _make


@pytest.fixture
def idem_key():
    """Gera Idempotency-Keys únicas por chamada."""
    return lambda: f"test-key-{next(_key_seq)}"
