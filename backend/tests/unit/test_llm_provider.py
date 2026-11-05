import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool

from app.core.config import Settings
from app.services.llm_provider import GroqProvider


class FakeBoundModel:
    async def ainvoke(self, messages):
        return AIMessage(content="ok")


class FakeChatModel:
    def __init__(self):
        self.bound_tools = None
        self.tool_choice = None

    def bind_tools(self, tools, *, tool_choice):
        self.bound_tools = tools
        self.tool_choice = tool_choice
        return FakeBoundModel()


class FailingChatModel:
    def bind_tools(self, tools, *, tool_choice):
        raise RuntimeError("simulated provider failure")


class RateLimitError(Exception):
    status_code = 429

    def __init__(self, retry_after=None, message="rate limit exceeded"):
        self.response = type("Response", (), {"status_code": 429, "headers": {}})()
        if retry_after is not None:
            self.response.headers["Retry-After"] = retry_after
        super().__init__(message)


class RetryingChatModel:
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0
        self.messages_seen = []

    def bind_tools(self, tools, *, tool_choice):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.messages_seen.append(list(messages))
        if self.failures:
            raise self.failures.pop(0)
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_groq_provider_uses_configured_model_and_binds_tools(monkeypatch) -> None:
    fake_model = FakeChatModel()
    captured: dict = {}

    def fake_chat_groq(**kwargs):
        captured.update(kwargs)
        return fake_model

    monkeypatch.setattr("app.services.llm_provider.ChatGroq", fake_chat_groq)

    async def read_only_tool() -> str:
        return "ok"

    tool = StructuredTool.from_function(
        coroutine=read_only_tool,
        name="read_only_tool",
        description="A test read-only tool.",
    )
    provider = GroqProvider(Settings(groq_api_key="test-key"))

    response = await provider.ainvoke([], [tool])

    assert response.content == "ok"
    assert captured["model"] == "openai/gpt-oss-20b"
    assert captured["temperature"] == 0
    assert captured["max_retries"] == 0
    assert fake_model.bound_tools == [tool]
    assert fake_model.tool_choice == "auto"
    assert captured["max_tokens"] == 2048
    assert captured["reasoning_effort"] == "low"
    assert captured["model_kwargs"] == {"include_reasoning": False}


def test_groq_model_can_be_overridden() -> None:
    settings = Settings(groq_model="custom/model")

    assert settings.groq_model == "custom/model"


def test_groq_reasoning_effort_can_be_configured() -> None:
    settings = Settings(groq_reasoning_effort="medium")

    assert settings.groq_reasoning_effort == "medium"


@pytest.mark.asyncio
async def test_groq_provider_logs_original_exception(caplog) -> None:
    provider = GroqProvider(Settings(groq_api_key="test-key"), model=FailingChatModel())

    with caplog.at_level("ERROR", logger="app.services.llm_provider"):
        with pytest.raises(Exception, match="Groq provider request failed"):
            await provider.ainvoke([], [])

    assert "Groq provider request failed; model=" in caplog.text
    assert "simulated provider failure" in caplog.text


@pytest.mark.asyncio
async def test_groq_provider_retries_rate_limit_using_retry_after(monkeypatch) -> None:
    model = RetryingChatModel([RateLimitError("0"), RateLimitError("0")])
    provider = GroqProvider(
        Settings(groq_api_key="test-key", groq_max_retries=2), model=model
    )
    delays = []
    async def record_delay(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_delay)

    response = await provider.ainvoke([], [])

    assert response.content == "ok"
    assert model.calls == 3
    assert delays == [0.0, 0.0]


@pytest.mark.asyncio
async def test_groq_provider_uses_retry_window_from_groq_error_message(monkeypatch) -> None:
    model = RetryingChatModel(
        [RateLimitError(message="Rate limit reached. Please try again in 17.805s.")]
    )
    provider = GroqProvider(Settings(groq_api_key="test-key", groq_max_retries=1), model=model)
    delays = []

    async def record_delay(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_delay)

    await provider.ainvoke([], [])

    assert delays == [17.805]


@pytest.mark.asyncio
async def test_groq_retries_reuse_the_complete_message_sequence(monkeypatch) -> None:
    model = RetryingChatModel([RateLimitError("0")])
    provider = GroqProvider(Settings(groq_api_key="test-key", groq_max_retries=1), model=model)
    delays = []

    async def record_delay(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_delay)
    messages = [HumanMessage(content="Review only the supplied diff.")]

    await provider.ainvoke(messages, [])

    assert model.calls == 2
    assert [[message.content for message in seen] for seen in model.messages_seen] == [
        ["Review only the supplied diff."],
        ["Review only the supplied diff."],
    ]
    assert delays == [0.0]


@pytest.mark.asyncio
async def test_groq_provider_uses_bounded_jittered_backoff(monkeypatch) -> None:
    model = RetryingChatModel([RateLimitError(), RateLimitError(), RateLimitError()])
    provider = GroqProvider(
        Settings(
            groq_api_key="test-key",
            groq_max_retries=2,
            groq_retry_base_seconds=2,
            groq_retry_max_seconds=5,
        ),
        model=model,
    )
    delays = []
    async def record_delay(delay):
        delays.append(delay)

    monkeypatch.setattr("app.services.llm_provider.asyncio.sleep", record_delay)
    monkeypatch.setattr("app.services.llm_provider.random.uniform", lambda low, high: 1.0)

    with pytest.raises(Exception, match="Groq provider request failed"):
        await provider.ainvoke([], [])

    assert model.calls == 3
    assert delays == [2.0, 4.0]
