import httpx
import pytest
from langchain_core.messages import AIMessage
from openai import BadRequestError
from pydantic import BaseModel, ValidationError

from aladeen.llm import LangChainRunner


class Verdict(BaseModel):
    complete: bool


def bad_request(message):
    response = httpx.Response(400, request=httpx.Request("POST", "https://example.test/chat"))
    return BadRequestError(message, response=response, body=None)


def test_unsupported_response_format_falls_back_and_remembers_tier(monkeypatch):
    runner = LangChainRunner({})
    calls = []

    def invoke(tier, messages, structured=None):
        calls.append((tier, structured))
        if structured:
            if tier == "quick":
                raise bad_request("This response_format type is unavailable now")
            return Verdict(complete=True)
        assert "JSON schema" in messages[0].content
        return AIMessage(content='{"complete": true}')

    monkeypatch.setattr(runner, "_invoke", invoke)
    for tier in ("quick", "quick", "deep"):
        assert runner.structured("System", "Research", Verdict, tier=tier).complete
    assert calls == [("quick", Verdict), ("quick", None), ("quick", None), ("deep", Verdict)]


def test_other_bad_request_propagates(monkeypatch):
    runner = LangChainRunner({})

    def invoke(*args, **kwargs):
        raise bad_request("Context window exceeded")

    monkeypatch.setattr(runner, "_invoke", invoke)
    with pytest.raises(BadRequestError, match="Context window"):
        runner.structured("System", "Research", Verdict)


def test_fallback_still_validates(monkeypatch):
    runner = LangChainRunner({})

    def invoke(tier, messages, structured=None):
        if structured:
            raise bad_request("response_format is not supported")
        return AIMessage(content='{"missing": true}')

    monkeypatch.setattr(runner, "_invoke", invoke)
    with pytest.raises(ValidationError):
        runner.structured("System", "Research", Verdict)
