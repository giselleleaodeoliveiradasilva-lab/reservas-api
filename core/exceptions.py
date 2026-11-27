"""
Hierarquia base de exceções de domínio.

As exceções de domínio NÃO conhecem HTTP: carregam apenas um `code` estável
(contrato com o cliente), uma mensagem e detalhes. O mapeamento categoria ->
status HTTP fica na camada HTTP (`core.exception_handler`).
"""

from typing import Any


class DomainError(Exception):
    code: str = "domain_error"
    default_message: str = "Erro de domínio."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class DomainValidationError(DomainError):
    """Entrada sintaticamente válida, mas que viola uma regra de negócio."""

    code = "validation_error"
    default_message = "Dados inválidos."


class NotFoundError(DomainError):
    code = "not_found"
    default_message = "Recurso não encontrado."


class ConflictError(DomainError):
    """A operação conflita com o estado atual dos dados."""

    code = "conflict"
    default_message = "A operação conflita com o estado atual."


class UnprocessableError(DomainError):
    """Requisição bem formada, mas semanticamente impossível de processar."""

    code = "unprocessable"
    default_message = "Não foi possível processar a requisição."
