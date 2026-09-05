"""LLM retry / fallback: llm/client.py"""

import pytest

import llm.client as client


class _Boom:
    def invoke(self, _messages):
        raise RuntimeError("simulated rate limit")


class _Ok:
    def invoke(self, _messages):
        return type("R", (), {"content": "  hello  "})()


def test_returns_stripped_content(monkeypatch):
    monkeypatch.setattr(client, "llm", _Ok())
    assert client.invoke_text(["m"]) == "hello"


def test_falls_back_after_retries(monkeypatch):
    monkeypatch.setattr(client, "llm", _Boom())
    out = client.invoke_text(["m"], retries=3, base_delay=0, fallback="SAFE")
    assert out == "SAFE"


def test_raises_without_fallback(monkeypatch):
    monkeypatch.setattr(client, "llm", _Boom())
    with pytest.raises(RuntimeError):
        client.invoke_text(["m"], retries=2, base_delay=0)
