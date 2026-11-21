"""T01 계약 테스트(docs/tasks/T01-project-skeleton.md, 11/21 승인)."""

from fastapi import Query


def assert_error_shape(body: dict, code: str) -> None:
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


# T01-1
def test_health_shape(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "agent": "scripted", "demoMode": True}


# T01-2
def test_unknown_path_is_not_found(client):
    res = client.get("/api/v1/no-such-path")
    assert res.status_code == 404
    assert_error_shape(res.json(), "NOT_FOUND")


def test_validation_error_shape(app, client):
    @app.get("/api/v1/_test/validate")
    def _validate(amount_krw: int = Query(alias="amountKrw")):
        return {"ok": True}

    res = client.get("/api/v1/_test/validate", params={"amountKrw": "abc"})
    assert res.status_code == 400
    body = res.json()
    assert_error_shape(body, "VALIDATION_ERROR")
    assert "amountKrw" in body["error"]["details"]["fields"]


def test_unhandled_exception_is_internal(app, client):
    @app.get("/api/v1/_test/boom")
    def _boom():
        raise RuntimeError("내부 정보: secret-value")

    res = client.get("/api/v1/_test/boom")
    assert res.status_code == 500
    body = res.json()
    assert_error_shape(body, "INTERNAL")
    assert "secret-value" not in res.text
