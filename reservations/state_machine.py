"""
Máquina de estados da reserva: funções puras, sem acesso ao banco.

    PENDENTE   -> CONFIRMADA | CANCELADA
    CONFIRMADA -> CONCLUIDA  | CANCELADA
    CANCELADA, CONCLUIDA: estados finais
"""

from reservations.exceptions import InvalidStatusTransition
from reservations.models import ReservationStatus as S

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    S.PENDENTE: frozenset({S.CONFIRMADA, S.CANCELADA}),
    S.CONFIRMADA: frozenset({S.CONCLUIDA, S.CANCELADA}),
    S.CANCELADA: frozenset(),
    S.CONCLUIDA: frozenset(),
}

# Estados que ocupam o horário do recurso (participam da checagem de conflito).
ACTIVE_STATUSES: frozenset[str] = frozenset({S.PENDENTE, S.CONFIRMADA})


def allowed_targets(from_status: str) -> frozenset[str]:
    return ALLOWED_TRANSITIONS.get(from_status, frozenset())


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in allowed_targets(from_status)


def ensure_transition_allowed(from_status: str, to_status: str) -> None:
    if not can_transition(from_status, to_status):
        raise InvalidStatusTransition(
            f"Não é permitido mudar de {from_status} para {to_status}.",
            details={
                "from_status": from_status,
                "to_status": to_status,
                "allowed_to_status": sorted(allowed_targets(from_status)),
            },
        )
