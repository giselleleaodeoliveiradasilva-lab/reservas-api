"""
Propagação do request_id para os logs.

Usa contextvars em vez de thread-local: funciona tanto em WSGI (threads) quanto
em código assíncrono, e cada requisição enxerga apenas o próprio valor.
"""

import contextvars
import logging

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(value: str) -> contextvars.Token:
    return _request_id_var.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Adiciona `record.request_id` a todo registro de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
