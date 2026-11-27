import pytest

from reservations.exceptions import InvalidStatusTransition
from reservations.models import ReservationStatus as S
from reservations.state_machine import ALLOWED_TRANSITIONS, can_transition, ensure_transition_allowed

ALLOWED = [
    (S.PENDENTE, S.CONFIRMADA),
    (S.PENDENTE, S.CANCELADA),
    (S.CONFIRMADA, S.CONCLUIDA),
    (S.CONFIRMADA, S.CANCELADA),
]

ALL_PAIRS = [(a, b) for a in S.values for b in S.values]
FORBIDDEN = [pair for pair in ALL_PAIRS if pair not in ALLOWED]


def test_every_status_has_a_transition_rule():
    assert set(ALLOWED_TRANSITIONS) == set(S.values)


@pytest.mark.parametrize(("from_status", "to_status"), ALLOWED)
def test_allowed_transitions(from_status, to_status):
    assert can_transition(from_status, to_status)
    ensure_transition_allowed(from_status, to_status)  # não levanta


@pytest.mark.parametrize(("from_status", "to_status"), FORBIDDEN)
def test_forbidden_transitions(from_status, to_status):
    assert not can_transition(from_status, to_status)
    with pytest.raises(InvalidStatusTransition) as exc_info:
        ensure_transition_allowed(from_status, to_status)
    assert exc_info.value.details["from_status"] == from_status
    assert exc_info.value.details["to_status"] == to_status


@pytest.mark.parametrize("terminal", [S.CANCELADA, S.CONCLUIDA])
def test_terminal_states_have_no_exit(terminal):
    assert ALLOWED_TRANSITIONS[terminal] == frozenset()
