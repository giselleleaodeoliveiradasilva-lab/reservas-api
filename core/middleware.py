import logging
import re
import time
import uuid

from core.logging import reset_request_id, set_request_id

logger = logging.getLogger("core.request")

REQUEST_ID_HEADER = "X-Request-Id"

# Só aceitamos o ID vindo do cliente se ele for "bem-comportado": evita injeção
# de conteúdo nos logs e valores gigantes. Caso contrário, geramos um novo.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._\-]{1,64}")


class RequestIdMiddleware:
    """
    Garante um identificador por requisição:
    - reaproveita o `X-Request-Id` recebido (se válido) ou gera um UUID;
    - expõe em `request.request_id` e no contexto de logging;
    - devolve o mesmo valor no cabeçalho da resposta;
    - registra uma linha de log de acesso com status e duração.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.request_id = request_id

        token = set_request_id(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            duration_ms = (time.monotonic() - started) * 1000
            response[REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )
            return response
        finally:
            reset_request_id(token)
