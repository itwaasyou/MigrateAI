import asyncio
import json

import httpx
import pytest

from migrateai import ai


def test_generate_calls_gemini_api(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "gemini-test-model")
    captured = {}

    def respond(request):
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 4,
                },
            },
        )

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        ai.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    result = asyncio.run(ai.generate("system prompt", "user prompt"))

    request = captured["request"]
    assert request.url.host == "generativelanguage.googleapis.com"
    assert request.headers["x-goog-api-key"] == "test-key"
    assert request.url.path.endswith("/models/gemini-test-model:generateContent")
    payload = json.loads(request.content)
    assert payload["system_instruction"]["parts"][0]["text"] == "system prompt"
    assert payload["contents"][0]["parts"][0]["text"] == "user prompt"
    assert result.body == '{"ok":true}'
    assert result.prompt_tokens == 12
    assert result.output_tokens == 4


def test_generate_retries_once_after_gemini_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "gemini-test-model")
    calls = []
    success = httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]},
    )

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return success

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        ai.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    result = asyncio.run(ai.generate("system prompt", "user prompt"))

    assert result.body == '{"ok":true}'
    assert len(calls) == 2


def test_validate_claims_accepts_citation_subranges():
    chunks = [
        {
            "file": "src/services/userService.ts",
            "start_line": 1,
            "end_line": 7,
            "excerpt": "retrieved lines",
        }
    ]
    body = json.dumps(
        {
            "claims": [
                {
                    "claim": "registerUser checks whether the user already exists.",
                    "type": "fact",
                    "confidence": 0.95,
                    "evidence": [
                        {
                            "file": "src/services/userService.ts",
                            "start_line": "3",
                            "end_line": "5",
                        }
                    ],
                }
            ]
        }
    )

    result = ai.validate_claims(body, chunks)

    assert result["claims"][0]["evidence"] == [
        {
            "file": "src/services/userService.ts",
            "start_line": 3,
            "end_line": 5,
        }
    ]


def test_generate_requires_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        asyncio.run(ai.generate("system prompt", "user prompt"))
