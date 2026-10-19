import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def make(client, **kw):
    body = {"title": "Write Jenkinsfile", "priority": "high"}
    body.update(kw)
    return client.post("/api/tasks", json=body)


def test_homepage_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"DEVOPS TASK TRACKER" in r.data


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "healthy"
    assert {"version", "environment"} <= set(body)


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200 and r.get_json()["status"] == "ready"


def test_env_from_app_env(monkeypatch, client):
    monkeypatch.setenv("APP_ENV", "qa")
    assert client.get("/health").get_json()["environment"] == "QA"
    monkeypatch.setenv("APP_ENV", "nonsense")
    assert client.get("/health").get_json()["environment"] == "DEV"


def test_list_empty(client):
    r = client.get("/api/tasks")
    assert r.status_code == 200
    assert r.get_json() == {"tasks": [], "summary": {"total": 0, "pending": 0, "completed": 0}}


def test_create_task(client):
    r = make(client)
    assert r.status_code == 201
    t = r.get_json()
    assert t["title"] == "Write Jenkinsfile" and t["completed"] is False and t["priority"] == "high"
    assert client.get("/api/tasks").get_json()["summary"]["total"] == 1


def test_complete_and_edit_task(client):
    tid = make(client).get_json()["id"]
    r = client.patch(f"/api/tasks/{tid}", json={"completed": True})
    assert r.status_code == 200 and r.get_json()["completed"] is True
    r = client.patch(f"/api/tasks/{tid}", json={"title": "Renamed", "priority": "low"})
    assert r.get_json()["title"] == "Renamed" and r.get_json()["priority"] == "low"
    s = client.get("/api/tasks").get_json()["summary"]
    assert s == {"total": 1, "pending": 0, "completed": 1}


def test_delete_task(client):
    tid = make(client).get_json()["id"]
    assert client.delete(f"/api/tasks/{tid}").status_code == 204
    assert client.get("/api/tasks").get_json()["tasks"] == []


@pytest.mark.parametrize("body", [
    {}, {"title": ""}, {"title": "   "}, {"title": 5}, {"title": "x" * 121},
    {"title": "ok", "priority": "urgent"}, {"title": "ok", "completed": "yes"},
    {"title": "ok", "extra": 1}, {"title": "ok", "description": "d" * 501}, [],
])
def test_create_invalid(client, body):
    r = client.post("/api/tasks", json=body)
    assert r.status_code == 400 and "error" in r.get_json()


def test_create_non_json(client):
    r = client.post("/api/tasks", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_patch_invalid(client):
    tid = make(client).get_json()["id"]
    assert client.patch(f"/api/tasks/{tid}", json={}).status_code == 400
    assert client.patch(f"/api/tasks/{tid}", json={"completed": "x"}).status_code == 400
    assert client.patch(f"/api/tasks/{tid}", json={"title": ""}).status_code == 400


def test_unknown_ids(client):
    assert client.patch("/api/tasks/abcdef123456", json={"completed": True}).status_code == 404
    assert client.delete("/api/tasks/abcdef123456").status_code == 404
    assert client.patch("/api/tasks/not-an-id", json={"completed": True}).status_code == 404
    assert client.delete("/api/tasks/not-an-id").status_code == 404


def test_unknown_route_and_method(client):
    assert client.get("/nope").status_code == 404
    assert client.get("/nope").get_json()["error"]
    assert client.put("/api/tasks").status_code == 405


def test_metrics(client):
    client.get("/health")
    make(client)
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "http_requests_total" in text
    assert "http_request_duration_seconds_bucket" in text
    assert "app_info" in text
    assert 'endpoint="/health"' in text
