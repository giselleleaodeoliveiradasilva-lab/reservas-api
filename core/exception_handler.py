"""
Tratamento centralizado de erros da API.

Todo erro sai no mesmo formato:

    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}

Exceções inesperadas são logadas com traceback, mas o cliente recebe apenas uma
mensagem genérica: detalhes internos nunca vazam na resposta.
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import set_rollback

from core.exceptions import (
    ConflictError,
    DomainError,
    DomainValidationError,
    NotFoundError,
    UnprocessableError,
)
from core.logging import get_request_id

logger = logging.getLogger(__name__)

# Ordem importa: a primeira categoria compatível (isinstance) define o status.
_DOMAIN_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (DomainValidationError, status.HTTP_400_BAD_REQUEST),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (UnprocessableError, status.HTTP_422_UNPROCESSABLE_ENTITY),
)

_DRF_CODES: dict[type[drf_exceptions.APIException], tuple[str, str]] = {
    drf_exceptions.ValidationError: ("validation_error", "Dados inválidos."),
    drf_exceptions.ParseError: ("malformed_request", "Corpo da requisição malformado."),
    drf_exceptions.NotFound: ("not_found", "Recurso não encontrado."),
    drf_exceptions.MethodNotAllowed: ("method_not_allowed", "Método não permitido."),
    drf_exceptions.UnsupportedMediaType: ("unsupported_media_type", "Tipo de conteúdo não suportado."),
    drf_exceptions.NotAcceptable: ("not_acceptable", "Formato de resposta não suportado."),
}


def build_error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


def _error_response(http_status: int, code: str, message: str, details: Any = None) -> Response:
    return Response(build_error_body(code, message, details), status=http_status)


def _domain_status(exc: DomainError) -> int:
    for category, http_status in _DOMAIN_STATUS:
        if isinstance(exc, category):
            return http_status
    return status.HTTP_400_BAD_REQUEST


def _drf_details(exc: drf_exceptions.APIException) -> Any:
    if isinstance(exc, drf_exceptions.ValidationError):
        detail = exc.detail
        return detail if isinstance(detail, dict) else {"non_field_errors": detail}
    return {}


def api_exception_handler(exc: Exception, context: dict) -> Response:
    # Garante rollback caso exista uma transação aberta pela requisição.
    set_rollback()

    if isinstance(exc, DomainError):
        http_status = _domain_status(exc)
        logger.info("domain_error code=%s status=%s message=%s", exc.code, http_status, exc.message)
        return _error_response(http_status, exc.code, exc.message, exc.details)

    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    if isinstance(exc, drf_exceptions.APIException):
        code, message = _DRF_CODES.get(type(exc), (str(exc.default_code), str(exc.default_detail)))
        response = _error_response(exc.status_code, code, message, _drf_details(exc))
        if isinstance(exc, drf_exceptions.Throttled) and exc.wait:
            response["Retry-After"] = str(int(exc.wait))
        return response

    logger.exception("unhandled_exception type=%s", type(exc).__name__)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Erro interno inesperado. Informe o request_id ao suporte.",
    )
