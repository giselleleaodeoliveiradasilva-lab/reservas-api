import pytest

from reservations.api.serializers import ReservationSerializer
from reservations.models import Reservation, ReservationStatus as S
from reservations.state_machine import ALLOWED_TRANSITIONS


@pytest.mark.parametrize("status", S.values)
def test_allowed_transitions_mirror_the_state_machine(status):
    data = ReservationSerializer(Reservation(status=status)).data
    assert data["allowed_transitions"] == sorted(ALLOWED_TRANSITIONS[status])


def test_terminal_status_exposes_no_transitions():
    assert ReservationSerializer(Reservation(status=S.CANCELADA)).data["allowed_transitions"] == []
