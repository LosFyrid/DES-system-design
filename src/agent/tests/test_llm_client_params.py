"""
Unit tests for LLMClient request parameter compatibility.

Focus: OpenAI GPT-5.* reasoning mode disallows sampling params such as temperature
when reasoning_effort is enabled. We enforce that in LLMClient so production
doesn't fail with runtime 400s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest
from pytest import MonkeyPatch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class _DummyMessage:
    content: str


@dataclass
class _DummyChoice:
    message: _DummyMessage


@dataclass
class _DummyResponse:
    choices: list[_DummyChoice]


class _DummyChatCompletions:
    def __init__(self, outcomes: Optional[list[Any]] = None):
        self.last_params: Optional[Dict[str, Any]] = None
        self.calls = 0
        self.outcomes = list(outcomes or [])

    def create(self, **params):  # noqa: ANN003 - matches OpenAI client's API
        self.calls += 1
        self.last_params = params
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return _DummyResponse(choices=[_DummyChoice(message=_DummyMessage(content="ok"))])


class _DummyChat:
    def __init__(self, outcomes: Optional[list[Any]] = None):
        self.completions = _DummyChatCompletions(outcomes=outcomes)


class _DummyOpenAI:
    def __init__(self, outcomes: Optional[list[Any]] = None):
        self.chat = _DummyChat(outcomes=outcomes)


class _StatusError(Exception):
    def __init__(self, status_code: int, message: str = "api error"):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _patch_openai_loader(monkeypatch: MonkeyPatch):
    for name in (
        "LLM_RETRY_ENABLED",
        "LLM_RETRY_MAX_ELAPSED_SECONDS",
        "LLM_RETRY_MAX_ATTEMPTS",
        "LLM_RETRY_INITIAL_DELAY_SECONDS",
        "LLM_RETRY_MAX_DELAY_SECONDS",
        "LLM_RETRY_EXPONENTIAL_BASE",
        "LLM_RETRY_JITTER",
        "LLM_RETRY_RESPECT_RETRY_AFTER",
        "LLM_RETRY_SDK_MAX_RETRIES",
        "OPENAI_SDK_MAX_RETRIES",
        "LLM_RETRY_STATUS_CODES",
    ):
        monkeypatch.delenv(name, raising=False)

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = _DummyChat()

    monkeypatch.setattr("agent.utils.llm_client._load_openai_class", lambda: _FakeOpenAI)


def test_langfuse_requested_without_credentials_falls_back(monkeypatch: MonkeyPatch):
    from agent.utils.llm_client import LLMClient

    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = _DummyChat()

    monkeypatch.setattr("agent.utils.llm_client._load_openai_class", lambda: _FakeOpenAI)

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    assert llm.langfuse_enabled is False
    assert isinstance(llm.client, _FakeOpenAI)
    assert llm.client.kwargs["api_key"] == "sk-test"
    assert llm.client.kwargs["base_url"] == "https://api.openai.com/v1"


def test_langfuse_requested_with_credentials_uses_langfuse_client(monkeypatch: MonkeyPatch):
    from agent.utils.llm_client import LLMClient

    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    class _FakeLangfuseOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = _DummyChat()

    monkeypatch.setattr(
        "agent.utils.llm_client._load_langfuse_openai_class",
        lambda: _FakeLangfuseOpenAI,
    )

    llm = LLMClient(
        provider="dashscope",
        model="qwen-plus",
        api_key="dash-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert llm.langfuse_enabled is True
    assert isinstance(llm.client, _FakeLangfuseOpenAI)
    assert llm.client.kwargs["api_key"] == "dash-test"
    assert llm.client.kwargs["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_openai_reasoning_effort_drops_temperature():
    from agent.utils.llm_client import LLMClient

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        temperature=0.1,
        max_tokens=1234,
        reasoning_effort="medium",
    )

    # Replace network client with dummy
    dummy = _DummyOpenAI()
    llm.client = dummy  # type: ignore[assignment]

    out = llm.chat("hello", temperature=0.9)  # override should be ignored
    assert out == "ok"

    params = dummy.chat.completions.last_params
    assert params is not None
    assert params["model"] == "gpt-5.2"
    assert params["reasoning_effort"] == "medium"

    # OpenAI uses max_completion_tokens, and must NOT send temperature
    assert params.get("max_completion_tokens") == 1234
    assert "temperature" not in params


def test_openai_reasoning_none_keeps_temperature():
    from agent.utils.llm_client import LLMClient

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        temperature=0.2,
        max_tokens=200,
        reasoning_effort="none",
    )
    dummy = _DummyOpenAI()
    llm.client = dummy  # type: ignore[assignment]

    _ = llm.chat("hi")
    params = dummy.chat.completions.last_params
    assert params is not None
    assert params["reasoning_effort"] == "none"
    assert params["temperature"] == pytest.approx(0.2)
    assert params["max_completion_tokens"] == 200


def test_dashscope_uses_max_tokens_and_temperature():
    from agent.utils.llm_client import LLMClient

    llm = LLMClient(
        provider="dashscope",
        model="qwen-plus",
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.3,
        max_tokens=321,
    )
    dummy = _DummyOpenAI()
    llm.client = dummy  # type: ignore[assignment]

    _ = llm.chat("hi")
    params = dummy.chat.completions.last_params
    assert params is not None
    assert params["max_tokens"] == 321
    assert params["temperature"] == pytest.approx(0.3)


def test_openai_client_disables_sdk_retries_by_default():
    from agent.utils.llm_client import LLMClient

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    assert llm.client.kwargs["max_retries"] == 0
    assert llm.retry_policy.max_elapsed_seconds == pytest.approx(600.0)


def test_retryable_status_uses_project_exponential_backoff(monkeypatch: MonkeyPatch):
    import agent.utils.llm_retry as llm_retry
    from agent.utils.llm_client import LLMClient

    sleeps: list[float] = []
    monkeypatch.setattr(llm_retry.random, "uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(llm_retry.time, "sleep", lambda seconds: sleeps.append(seconds))

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        retry_config={
            "max_elapsed_seconds": 600,
            "max_attempts": 3,
            "initial_delay_seconds": 2,
            "max_delay_seconds": 120,
            "jitter": 0,
        },
    )
    dummy = _DummyOpenAI(
        outcomes=[
            _StatusError(429, "rate limit"),
            _DummyResponse(choices=[_DummyChoice(message=_DummyMessage(content="recovered"))]),
        ]
    )
    llm.client = dummy  # type: ignore[assignment]

    out = llm.chat("retry please")

    assert out == "recovered"
    assert dummy.chat.completions.calls == 2
    assert sleeps == [pytest.approx(2.0)]


def test_non_retryable_status_is_not_retried(monkeypatch: MonkeyPatch):
    import agent.utils.llm_retry as llm_retry
    from agent.utils.llm_client import LLMClient

    sleeps: list[float] = []
    monkeypatch.setattr(llm_retry.time, "sleep", lambda seconds: sleeps.append(seconds))

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        retry_config={"max_attempts": 3, "jitter": 0},
    )
    dummy = _DummyOpenAI(outcomes=[_StatusError(400, "bad request")])
    llm.client = dummy  # type: ignore[assignment]

    with pytest.raises(_StatusError):
        llm.chat("do not retry")

    assert dummy.chat.completions.calls == 1
    assert sleeps == []


def test_retry_after_header_is_respected_and_capped(monkeypatch: MonkeyPatch):
    import agent.utils.llm_retry as llm_retry
    from agent.utils.llm_client import LLMClient

    class _RateLimitWithHeaders(_StatusError):
        def __init__(self):
            super().__init__(429, "rate limit")
            self.headers = {"retry-after": "300"}

    sleeps: list[float] = []
    monkeypatch.setattr(llm_retry.time, "sleep", lambda seconds: sleeps.append(seconds))

    llm = LLMClient(
        provider="openai",
        model="gpt-5.2",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        retry_config={
            "max_attempts": 3,
            "max_elapsed_seconds": 600,
            "max_delay_seconds": 120,
            "jitter": 0,
        },
    )
    dummy = _DummyOpenAI(
        outcomes=[
            _RateLimitWithHeaders(),
            _DummyResponse(choices=[_DummyChoice(message=_DummyMessage(content="ok after retry-after"))]),
        ]
    )
    llm.client = dummy  # type: ignore[assignment]

    assert llm.chat("respect retry-after") == "ok after retry-after"
    assert sleeps == [pytest.approx(120.0)]
