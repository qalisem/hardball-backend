"""Smoke tests for the Hardball API.

Run with: pytest tests/
"""
from app import create_app


def test_health():
    app = create_app()
    client = app.test_client()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_list_teams():
    app = create_app()
    client = app.test_client()
    r = client.get("/api/teams")
    assert r.status_code == 200
    data = r.get_json()
    assert "teams" in data
    abbrs = {t["abbr"] for t in data["teams"]}
    assert {"LAL", "BOS", "TOR", "GSW", "OKC"}.issubset(abbrs)


def test_get_team_found():
    app = create_app()
    client = app.test_client()
    r = client.get("/api/teams/TOR")
    assert r.status_code == 200
    team = r.get_json()
    assert team["abbr"] == "TOR"
    assert team["name"] == "Toronto Raptors"
    assert isinstance(team["roster"], list)


def test_get_team_lowercase_works():
    app = create_app()
    client = app.test_client()
    r = client.get("/api/teams/lal")
    assert r.status_code == 200
    assert r.get_json()["abbr"] == "LAL"


def test_get_team_not_found():
    app = create_app()
    client = app.test_client()
    r = client.get("/api/teams/XXX")
    assert r.status_code == 404


def test_chat_rejects_empty_messages():
    app = create_app()
    client = app.test_client()
    r = client.post("/api/chat", json={"messages": []})
    assert r.status_code == 400


def test_chat_rejects_bad_shape():
    app = create_app()
    client = app.test_client()
    r = client.post("/api/chat", json={"messages": [{"role": "user"}]})
    assert r.status_code == 400


def test_chat_missing_key_returns_500(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app()
    client = app.test_client()
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 500
