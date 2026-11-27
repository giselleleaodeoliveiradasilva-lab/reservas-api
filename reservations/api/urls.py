from django.urls import path

from reservations.api import views

urlpatterns = [
    path("resources/", views.ResourceListCreateView.as_view(), name="resource-list"),
    path("resources/<int:pk>/", views.ResourceDetailView.as_view(), name="resource-detail"),
    path("reservations/", views.ReservationListCreateView.as_view(), name="reservation-list"),
    path("reservations/<int:pk>/", views.ReservationDetailView.as_view(), name="reservation-detail"),
    path(
        "reservations/<int:pk>/transitions/",
        views.ReservationTransitionView.as_view(),
        name="reservation-transition",
    ),
    path("reservations/<int:pk>/history/", views.ReservationHistoryView.as_view(), name="reservation-history"),
]
