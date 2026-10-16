"""AWS Lambda entry point (Lambda Function URL, payload format 2.0).

Routes:
  GET  /           -> chat page (static/index.html)
  GET  /health     -> {"ok": true}
  POST /api/chat   -> run the deep agent. Requires header x-access-code.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
from pathlib import Path

MAX_MESSAGES = 40
MAX_CHARS = 4000
INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


def _json(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def _load_openai_key() -> bool:
    """Use OPENAI_API_KEY if set, else read it once from SSM Parameter Store."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    param = os.environ.get("OPENAI_KEY_PARAM")
    if not param:
        return False
    import boto3  # bundled with the Lambda Python runtime

    value = boto3.client("ssm").get_parameter(Name=param, WithDecryption=True)["Parameter"]["Value"]
    os.environ["OPENAI_API_KEY"] = value
    return True


def _validate(payload) -> list[dict]:
    msgs = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(msgs, list) or not msgs:
        raise ValueError("Body must be JSON like {\"messages\": [{\"role\": \"user\", \"content\": \"...\"}]}")
    if len(msgs) > MAX_MESSAGES:
        raise ValueError(f"Too many messages (max {MAX_MESSAGES}). Start a new chat.")
    clean = []
    for m in msgs:
        role, content = (m or {}).get("role"), (m or {}).get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            raise ValueError("Each message needs role 'user' or 'assistant' and non-empty text content")
        if len(content) > MAX_CHARS * (3 if role == "assistant" else 1):
            raise ValueError(f"A message is too long (max {MAX_CHARS} characters)")
        clean.append({"role": role, "content": content})
    if clean[-1]["role"] != "user":
        raise ValueError("The last message must be from the user")
    return clean


def lambda_handler(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "GET").upper()
    path = event.get("rawPath") or "/"

    if method == "GET" and path in ("/", "/index.html"):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"},
            "body": INDEX_HTML,
        }
    if method == "GET" and path == "/health":
        return _json(200, {"ok": True})
    if path != "/api/chat":
        return _json(404, {"error": "Not found"})
    if method != "POST":
        return _json(405, {"error": "Use POST"})

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    expected = os.environ.get("ACCESS_CODE", "")
    if not expected or not hmac.compare_digest(headers.get("x-access-code", ""), expected):
        return _json(401, {"error": "Wrong or missing access code"})

    try:
        raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        messages = _validate(json.loads(raw or "{}"))
    except (ValueError, UnicodeDecodeError) as exc:
        return _json(400, {"error": str(exc)})

    try:
        if not _load_openai_key():
            return _json(500, {"error": "OpenAI key is not configured on the server"})
        from app.agent import run_chat  # heavy import, only for chat requests

        return _json(200, run_chat(messages))
    except Exception as exc:  # noqa: BLE001
        print(f"Agent error: {exc!r}")
        return _json(502, {"error": f"Agent failed: {type(exc).__name__}: {exc}"[:500]})
