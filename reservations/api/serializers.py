"""
Serializers separados para entrada e saída.

Os de entrada são `Serializer` simples (não ModelSerializer) de propósito: eles
validam apenas formato/tipo. Regras de negócio e unicidade ficam no service e no
banco, assim um erro de duplicidade sempre vira 409, e nunca um 400 vindo de um
validador automático do DRF.
"""

from rest_framework import serializers

from reservations.models import Reservation, ReservationStatus, ReservationStatusHistory, Resource
from reservations.state_machine import allowed_targets


# --- Entrada ------------------------------------------------------------------

class ResourceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class ReservationCreateSerializer(serializers.Serializer):
    resource_id = serializers.IntegerField(min_value=1)
    customer_name = serializers.CharField(max_length=150)
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()


class ReservationTransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=ReservationStatus.choices)


# --- Saída --------------------------------------------------------------------

class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = fields


class ReservationSerializer(serializers.ModelSerializer):
    resource_id = serializers.IntegerField(read_only=True)
    # Derivado da máquina de estados: clientes não precisam conhecer (nem copiar)
    # as regras de transição. É informativo; o service continua validando cada
    # transição, pois o valor pode ficar desatualizado entre leitura e ação.
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "resource_id",
            "customer_name",
            "start_at",
            "end_at",
            "status",
            "allowed_transitions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_allowed_transitions(self, obj: Reservation) -> list[str]:
        return sorted(allowed_targets(obj.status))


class ReservationStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationStatusHistory
        fields = ["id", "from_status", "to_status", "changed_at", "idempotency_key", "request_id"]
        read_only_fields = fields
