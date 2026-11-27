"""
Execução idempotente de operações.

Estratégia ("reservar a chave primeiro"):

1. Se já existe registro para (scope, key): devolve a resposta salva, ou 422 se
   o payload for diferente.
2. Senão, abre uma transação e INSERE a chave antes de executar a operação.
   - Uma requisição concorrente com a mesma chave fica bloqueada no índice
     único até a primeira terminar (PostgreSQL e InnoDB se comportam igual).
     Depois do commit, ela recebe IntegrityError e devolve a resposta salva.
   - Se a primeira falhar (rollback), a chave some junto e a segunda segue
     normalmente.
3. Executa a operação e grava a resposta na MESMA transação: ou a operação e a
   chave são persistidas juntas, ou nenhuma das duas.

Só respostas de sucesso ficam salvas: um erro de negócio (ex.: conflito de
horário) desfaz a transação, e o cliente pode tentar de novo com a mesma chave.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction

from core.idempotency.exceptions import IdempotencyKeyReused, IdempotencyRequestInProgress
from core.idempotency.models import IdempotencyKey

Operation = Callable[[], tuple[int, Any]]


@dataclass(frozen=True)
class IdempotentResult:
    status_code: int
    body: Any
    replayed: bool


class _KeyAlreadyClaimed(Exception):
    pass


def compute_request_hash(payload: Any) -> str:
    """Hash estável: independe da ordem das chaves e do formato de datas."""
    canonical = json.dumps(payload, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execute_idempotent(*, key: str, scope: str, payload: Any, operation: Operation) -> IdempotentResult:
    request_hash = compute_request_hash(payload)

    stored = _find(scope=scope, key=key)
    if stored is not None:
        return _replay(stored, request_hash)

    try:
        with transaction.atomic():
            record = _claim(scope=scope, key=key, request_hash=request_hash)
            status_code, body = operation()
            record.response_status = status_code
            record.response_body = body
            record.save(update_fields=["response_status", "response_body"])
    except _KeyAlreadyClaimed:
        # Outra requisição com a mesma chave terminou primeiro.
        stored = _find(scope=scope, key=key)
        if stored is None:
            raise IdempotencyRequestInProgress() from None
        return _replay(stored, request_hash)

    return IdempotentResult(status_code=status_code, body=body, replayed=False)


def _find(*, scope: str, key: str) -> IdempotencyKey | None:
    return IdempotencyKey.objects.filter(scope=scope, key=key).first()


def _claim(*, scope: str, key: str, request_hash: str) -> IdempotencyKey:
    try:
        # Savepoint: no PostgreSQL um erro sem savepoint invalida a transação externa.
        with transaction.atomic():
            return IdempotencyKey.objects.create(scope=scope, key=key, request_hash=request_hash)
    except IntegrityError as exc:
        raise _KeyAlreadyClaimed() from exc


def _replay(stored: IdempotencyKey, request_hash: str) -> IdempotentResult:
    if stored.request_hash != request_hash:
        raise IdempotencyKeyReused(details={"idempotency_key": stored.key})
    if stored.response_status is None:
        raise IdempotencyRequestInProgress()
    return IdempotentResult(status_code=stored.response_status, body=stored.response_body, replayed=True)
