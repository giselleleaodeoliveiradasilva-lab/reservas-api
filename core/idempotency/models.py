from django.db import models


class IdempotencyKey(models.Model):
    """
    Registro de uma operação idempotente já executada.

    A unicidade de (scope, key) é garantida pelo banco: é ela que impede que
    duas requisições concorrentes com a mesma chave executem a operação duas vezes.
    """

    key = models.CharField(max_length=255)
    # Identifica a operação (ex.: "reservations.create"). Evita colisão de uma
    # mesma chave usada em endpoints diferentes.
    scope = models.CharField(max_length=100)
    # SHA-256 do payload canônico: detecta reuso da chave com dados diferentes.
    request_hash = models.CharField(max_length=64)
    # Preenchidos na mesma transação da operação; nunca ficam nulos após o commit.
    response_status = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="uniq_idempotency_scope_key"),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"
