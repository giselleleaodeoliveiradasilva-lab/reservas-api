from django.db import models
from django.db.models import F, Q


class ReservationStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    CONFIRMADA = "CONFIRMADA", "Confirmada"
    CANCELADA = "CANCELADA", "Cancelada"
    CONCLUIDA = "CONCLUIDA", "Concluída"


class Resource(models.Model):
    """Algo que pode ser reservado (sala, equipamento...)."""

    name = models.CharField(max_length=150)
    # Unicidade case/espaço-insensível de forma portável: a collation padrão do
    # MySQL ignora maiúsculas, a do PostgreSQL não. Em vez de depender da
    # collation (ou de índice funcional), guardamos a forma normalizada.
    normalized_name = models.CharField(max_length=255, editable=False)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["normalized_name"], name="uniq_resource_normalized_name"),
        ]

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join(name.split()).casefold()

    def save(self, *args, **kwargs):
        self.normalized_name = self.normalize_name(self.name)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "normalized_name"}
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Reservation(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="reservations")
    customer_name = models.CharField(max_length=150)
    # Intervalo semiaberto [start_at, end_at): uma reserva que termina às 10h
    # não conflita com outra que começa às 10h.
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDENTE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at", "id"]
        constraints = [
            # Última linha de defesa: a regra também vale para escritas fora do service.
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="reservation_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ReservationStatus.values),
                name="reservation_status_valid",
            ),
        ]
        indexes = [
            # Atende a busca de sobreposição (resource + intervalo) e o filtro por recurso.
            models.Index(fields=["resource", "start_at"], name="reservation_resource_start_idx"),
            models.Index(fields=["status", "start_at"], name="reservation_status_start_idx"),
        ]

    def __str__(self) -> str:
        return f"Reserva #{self.pk} ({self.status})"


class ReservationStatusHistory(models.Model):
    """Trilha de auditoria: uma linha por mudança de estado (incluindo a criação)."""

    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="history")
    # Nulo apenas no registro de criação.
    from_status = models.CharField(max_length=20, choices=ReservationStatus.choices, null=True)
    to_status = models.CharField(max_length=20, choices=ReservationStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["changed_at", "id"]
        indexes = [
            models.Index(fields=["reservation", "changed_at"], name="history_reservation_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reservation_id}: {self.from_status} -> {self.to_status}"
