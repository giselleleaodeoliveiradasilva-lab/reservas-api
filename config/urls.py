from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("reservations.api.urls")),
    path("", include("web.urls")),
]

# Respostas JSON também para rotas fora do DRF (ativas quando DEBUG=False).
handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
