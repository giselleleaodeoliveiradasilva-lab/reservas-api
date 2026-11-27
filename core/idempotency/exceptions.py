from core.exceptions import ConflictError, DomainValidationError, UnprocessableError


class IdempotencyKeyMissing(DomainValidationError):
    code = "idempotency_key_required"
    default_message = "O cabeçalho Idempotency-Key é obrigatório nesta operação."


class IdempotencyKeyInvalid(DomainValidationError):
    code = "idempotency_key_invalid"
    default_message = (
        "Idempotency-Key inválida: use de 1 a 255 caracteres entre letras, dígitos, '-', '_', '.' e ':'."
    )


class IdempotencyKeyReused(UnprocessableError):
    code = "idempotency_key_reused"
    default_message = "Esta Idempotency-Key já foi usada com um payload diferente."


class IdempotencyRequestInProgress(ConflictError):
    code = "idempotency_request_in_progress"
    default_message = "Uma requisição com esta Idempotency-Key ainda está em processamento. Tente novamente."
