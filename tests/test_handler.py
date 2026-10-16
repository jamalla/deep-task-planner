import json

import pytest

from app import handler


def ev(method="GET", path="/", body=None, code=None):
    e = {"rawPath": path, "requestContext": {"http": {"method": method}}, "headers": {}}
    if code is not None:
        e["headers"]["X-Access-Code"] = code
    if body is not None:
        e["body"] = json.dumps(body)
    return e


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_chat_page_served():
    r = handler.lambda_handler(ev(), None)
    assert r["statusCode"] == 200 and "Task Breakdown Coach" in r["body"]
    assert r["headers"]["Content-Type"].startswith("text/html")


def test_health_and_404():
    assert handler.lambda_handler(ev(path="/health"), None)["statusCode"] == 200
    assert handler.lambda_handler(ev(path="/nope"), None)["statusCode"] == 404


def test_requires_access_code():
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert handler.lambda_handler(ev("POST", "/api/chat", body), None)["statusCode"] == 401
    assert handler.lambda_handler(ev("POST", "/api/chat", body, "wrong"), None)["statusCode"] == 401


@pytest.mark.parametrize("body", [
    {}, {"messages": []}, {"messages": [{"role": "system", "content": "x"}]},
    {"messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]},
    {"messages": [{"role": "user", "content": "x" * 5000}]},
])
def test_rejects_bad_input(body):
    assert handler.lambda_handler(ev("POST", "/api/chat", body, "secret"), None)["statusCode"] == 400


def test_happy_path(monkeypatch):
    import app.agent

    monkeypatch.setattr(app.agent, "run_chat", lambda msgs: {"reply": "ok", "todos": [], "tools_used": []})
    r = handler.lambda_handler(ev("POST", "/api/chat", {"messages": [{"role": "user", "content": "plan"}]}, "secret"), None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["reply"] == "ok"
