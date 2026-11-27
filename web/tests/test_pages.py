"""As páginas apenas entregam HTML + JS; não acessam o banco (sem django_db)."""

import pytest


@pytest.mark.parametrize(
    ("url", "script"),
    [
        ("/", "web/js/reservation-list.js"),
        ("/reservas/nova/", "web/js/reservation-form.js"),
        ("/reservas/42/", "web/js/reservation-detail.js"),
        ("/recursos/", "web/js/resources.js"),
    ],
)
def test_pages_render_with_their_script(client, url, script):
    response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert script in response.content.decode()
    assert response["X-Request-Id"]


def test_detail_page_passes_reservation_id_to_js(client):
    response = client.get("/reservas/42/")
    assert 'data-reservation-id="42"' in response.content.decode()
