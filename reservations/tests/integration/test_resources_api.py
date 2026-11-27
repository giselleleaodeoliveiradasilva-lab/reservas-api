import pytest

from reservations import services

pytestmark = pytest.mark.django_db

URL = "/api/v1/resources/"


def assert_error(response, status_code, code):
    assert response.status_code == status_code, response.content
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response["X-Request-Id"]
    return body["error"]


def test_create_resource(api_client):
    response = api_client.post(URL, {"name": "Auditório", "description": "120 lugares"}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Auditório"
    assert body["description"] == "120 lugares"
    assert {"id", "created_at", "updated_at"} <= set(body)


def test_duplicate_resource_returns_409(api_client, resource):
    response = api_client.post(URL, {"name": "SALA AZUL"}, format="json")
    assert_error(response, 409, "resource_already_exists")


def test_validation_error_returns_400_with_field_details(api_client):
    response = api_client.post(URL, {"description": "sem nome"}, format="json")
    error = assert_error(response, 400, "validation_error")
    assert "name" in error["details"]


def test_malformed_json_returns_400(api_client):
    response = api_client.generic("POST", URL, "{nao é json", content_type="application/json")
    assert_error(response, 400, "malformed_request")


def test_get_resource(api_client, resource):
    response = api_client.get(f"{URL}{resource.pk}/")
    assert response.status_code == 200
    assert response.json()["id"] == resource.pk


def test_get_unknown_resource_returns_404(api_client):
    response = api_client.get(f"{URL}999999/")
    error = assert_error(response, 404, "resource_not_found")
    assert error["details"] == {"resource_id": 999999}


def test_list_resources_is_paginated(api_client):
    for i in range(3):
        services.create_resource(name=f"Sala {i}")

    response = api_client.get(URL, {"page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert len(body["results"]) == 2
    assert body["next"] is not None


def test_method_not_allowed_uses_standard_format(api_client, resource):
    response = api_client.delete(f"{URL}{resource.pk}/")
    assert_error(response, 405, "method_not_allowed")


def test_unexpected_error_hides_internal_details(api_client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("segredo interno: senha=123")

    monkeypatch.setattr(services, "create_resource", boom)

    response = api_client.post(URL, {"name": "X"}, format="json")

    error = assert_error(response, 500, "internal_error")
    assert "segredo" not in response.content.decode()
    assert "Traceback" not in response.content.decode()
    assert error["details"] == {}
