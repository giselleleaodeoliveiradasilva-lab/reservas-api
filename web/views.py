"""
Páginas da interface web.

Estas views só entregam o HTML "vazio": não consultam o banco nem chamam
services. Os dados são buscados pelo JavaScript na API pública (/api/v1/), de
modo que a interface é um cliente como qualquer outro e não existe um segundo
caminho de acesso aos dados que possa contornar as regras do backend.
"""

from django.views.generic import TemplateView


class ReservationListPage(TemplateView):
    template_name = "web/reservation_list.html"


class ReservationCreatePage(TemplateView):
    template_name = "web/reservation_form.html"


class ReservationDetailPage(TemplateView):
    # O `pk` da URL vai para o contexto e é repassado ao JS via data-attribute.
    template_name = "web/reservation_detail.html"


class ResourcesPage(TemplateView):
    template_name = "web/resources.html"
