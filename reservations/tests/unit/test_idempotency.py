from datetime import UTC, datetime

import pytest

from core.idempotency.exceptions import IdempotencyKeyReused
from core.idempotency.models import IdempotencyKey
from core.idempotency.services import compute_request_hash, execute_idempotent


def test_hash_ignores_key_order():
    assert compute_request_hash({"a": 1, "b": 2}) == compute_request_hash({"b": 2, "a": 1})


def test_hash_changes_with_payload():
    assert compute_request_hash({"a": 1}) != compute_request_hash({"a": 2})


def test_hash_supports_datetimes():
    moment = datetime(2030, 1, 1, 10, tzinfo=UTC)
    assert compute_request_hash({"t": moment}) == compute_request_hash({"t": moment})


@pytest.mark.django_db
class TestExecuteIdempotent:
    def test_first_call_runs_operation_and_stores_response(self):
        calls = []

        def op():
            calls.append(1)
            return 201, {"id": 1}

        result = execute_idempotent(key="k1", scope="s", payload={"x": 1}, operation=op)

        assert (result.status_code, result.body, result.replayed) == (201, {"id": 1}, False)
        assert calls == [1]
        stored = IdempotencyKey.objects.get(scope="s", key="k1")
        assert stored.response_status == 201
        assert stored.response_body == {"id": 1}

    def test_replay_returns_stored_response_without_running_again(self):
        calls = []

        def op():
            calls.append(1)
            return 201, {"id": len(calls)}

        execute_idempotent(key="k1", scope="s", payload={"x": 1}, operation=op)
        result = execute_idempotent(key="k1", scope="s", payload={"x": 1}, operation=op)

        assert (result.status_code, result.body, result.replayed) == (201, {"id": 1}, True)
        assert calls == [1]

    def test_same_key_with_different_payload_is_rejected(self):
        execute_idempotent(key="k1", scope="s", payload={"x": 1}, operation=lambda: (201, {}))
        with pytest.raises(IdempotencyKeyReused):
            execute_idempotent(key="k1", scope="s", payload={"x": 2}, operation=lambda: (201, {}))

    def test_same_key_in_different_scopes_is_independent(self):
        execute_idempotent(key="k1", scope="a", payload={}, operation=lambda: (201, {"scope": "a"}))
        result = execute_idempotent(key="k1", scope="b", payload={}, operation=lambda: (201, {"scope": "b"}))
        assert result.body == {"scope": "b"}
        assert not result.replayed

    def test_failed_operation_does_not_consume_the_key(self):
        def failing():
            raise RuntimeError("falhou")

        with pytest.raises(RuntimeError):
            execute_idempotent(key="k1", scope="s", payload={}, operation=failing)

        assert not IdempotencyKey.objects.filter(key="k1").exists()
        result = execute_idempotent(key="k1", scope="s", payload={}, operation=lambda: (201, {"ok": True}))
        assert result.body == {"ok": True}
        assert not result.replayed
