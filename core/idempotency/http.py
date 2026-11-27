"""Adaptadores HTTP da idempotência: leitura do cabeçalho e montagem da Response."""

import re
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response

from core.idempotency.exceptions import IdempotencyKeyInvalid, IdempotencyKeyMissing
from core.idempotency.services import Operation, execute_idempotent

IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"

_VALID_KEY = re.compile(r"[A-Za-z0-9_\-.:]{1,255}")


def require_idempotency_key(request: Request) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if not key:
        raise IdempotencyKeyMissing()
    if not _VALID_KEY.fullmatch(key):
        raise IdempotencyKeyInvalid()
    return key


def idempotent_response(*, key: str, scope: str, payload: Any, operation: Operation) -> Response:
    result = execute_idempotent(key=key, scope=scope, payload=payload, operation=operation)
    response = Response(result.body, status=result.status_code)
    if result.replayed:
        response[REPLAYED_HEADER] = "true"
    return response
