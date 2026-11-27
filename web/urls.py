from django.urls import path

from web import views

app_name = "web"

urlpatterns = [
    path("", views.ReservationListPage.as_view(), name="reservation-list"),
    path("reservas/nova/", views.ReservationCreatePage.as_view(), name="reservation-create"),
    path("reservas/<int:pk>/", views.ReservationDetailPage.as_view(), name="reservation-detail"),
    path("recursos/", views.ResourcesPage.as_view(), name="resources"),
]
