"""Handlers JSON para erros fora das views DRF (ex.: rota inexistente)."""

from django.http import JsonResponse

from core.exception_handler import build_error_body


def not_found(request, exception=None):
    return JsonResponse(build_error_body("not_found", "Rota não encontrada."), status=404)


def server_error(request):
    return JsonResponse(
        build_error_body("internal_error", "Erro interno inesperado. Informe o request_id ao suporte."),
        status=500,
    )
