from core.exceptions import ConflictError, DomainValidationError, NotFoundError


class ResourceNotFound(NotFoundError):
    code = "resource_not_found"
    default_message = "Recurso não encontrado."


class ResourceAlreadyExists(ConflictError):
    code = "resource_already_exists"
    default_message = "Já existe um recurso com este nome."


class ReservationNotFound(NotFoundError):
    code = "reservation_not_found"
    default_message = "Reserva não encontrada."


class InvalidReservationPeriod(DomainValidationError):
    code = "invalid_reservation_period"
    default_message = "Período de reserva inválido."


class ReservationConflict(ConflictError):
    code = "reservation_conflict"
    default_message = "O recurso já possui uma reserva ativa que se sobrepõe a este período."


class InvalidStatusTransition(ConflictError):
    code = "invalid_status_transition"
    default_message = "Transição de status não permitida."
