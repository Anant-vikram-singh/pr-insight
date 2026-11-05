import json

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.core.config import Settings
from app.schemas.github import PullRequestRequest
from app.services.github_service import GitHubService
from app.services.review_service import ReviewEngine, ReviewOutputError


class FakeProvider:
    def __init__(self, final_content: str | None = None):
        self.calls = 0
        self.messages = []
        self.final_content = (
            final_content
            if final_content is not None
            else json.dumps(
                {
                    "summary": "The changed endpoint has one review concern.",
                    "findings": [
                        {
                            "file_path": "app.py",
                            "line_start": 1,
                            "line_end": 1,
                            "severity": "medium",
                            "category": "testing",
                            "title": "Add endpoint coverage",
                            "explanation": "The new endpoint has no visible regression test in the changed files.",
                            "evidence": "The endpoint is introduced on the changed line.",
                            "suggested_fix": "Add a focused API test for the endpoint.",
                            "confidence": 0.8,
                            "certainty": "evidence_backed",
                        }
                    ],
                    "test_suggestions": ["Test the endpoint response."],
                }
            )
        )

    async def ainvoke(self, messages, tools):
        self.calls += 1
        self.messages.append(list(messages))
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "fetch_pr_metadata", "args": {}, "id": "call-1"}])
        if self.calls == 2:
            return AIMessage(content="", tool_calls=[{"name": "fetch_changed_files", "args": {}, "id": "call-2"}])
        if self.calls == 3:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "inspect_file_diff", "args": {"file_path": "app.py"}, "id": "call-3"}
                ]
            )
        return AIMessage(content=self.final_content)


def make_settings(**overrides) -> Settings:
    return Settings(github_api_base_url="https://api.github.test", **overrides)


def make_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/1"):
            return httpx.Response(
                200,
                json={
                    "title": "Add endpoint",
                    "body": "Untrusted PR text",
                    "state": "open",
                    "html_url": "https://github.com/example/repo/pull/1",
                    "user": {"login": "dev"},
                    "base": {"ref": "main", "sha": "base"},
                    "head": {"ref": "feature", "sha": "head"},
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "filename": "app.py",
                    "status": "added",
                    "additions": 1,
                    "deletions": 0,
                    "changes": 1,
                    "patch": "@@ -0,0 +1 @@\n+def endpoint():",
                }
            ],
        )

    return httpx.AsyncClient(
        base_url="https://api.github.test", transport=httpx.MockTransport(handler)
    )


@pytest.mark.asyncio
async def test_agent_calls_tools_and_validates_final_evidence() -> None:
    settings = make_settings()
    client = make_client()
    service = GitHubService(settings, client)
    provider = FakeProvider()
    engine = ReviewEngine(service, provider, settings)

    result = await engine.review(
        PullRequestRequest(url="https://github.com/example/repo/pull/1")
    )

    assert result.status == "completed"
    assert result.tool_calls == 3
    assert result.iterations == 4
    assert result.review.findings[0].file_path == "app.py"
    assert provider.calls == 4
    assert [message.tool_call_id for message in provider.messages[-1] if message.type == "tool"] == [
        "call-1",
        "call-2",
        "call-3",
    ]
    assert provider.messages[1][-1].type == "tool"
    assert provider.messages[1][-1].tool_call_id == "call-1"
    await client.aclose()


class MultipleToolCallProvider:
    def __init__(self):
        self.calls = 0
        self.messages = []

    async def ainvoke(self, messages, tools):
        self.calls += 1
        self.messages.append(list(messages))
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "fetch_pr_metadata", "args": {}, "id": "metadata-call"},
                    {"name": "fetch_changed_files", "args": {}, "id": "files-call"},
                ],
            )
        return AIMessage(
            content='{"summary":"No evidence-backed findings.","findings":[],"test_suggestions":[]}'
        )


class SingleResponseProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def ainvoke(self, messages, tools):
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_agent_executes_multiple_tool_calls_and_preserves_each_id() -> None:
    settings = make_settings()
    client = make_client()
    provider = MultipleToolCallProvider()
    engine = ReviewEngine(GitHubService(settings, client), provider, settings)

    result = await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))

    assert result.status == "completed"
    assert result.tool_calls == 2
    assert provider.calls == 2
    tool_messages = [message for message in provider.messages[1] if message.type == "tool"]
    assert [message.tool_call_id for message in tool_messages] == ["metadata-call", "files-call"]
    await client.aclose()


@pytest.mark.asyncio
async def test_tool_call_response_diagnostics_are_visible_without_logging_content(caplog) -> None:
    settings = make_settings()
    client = make_client()
    provider = MultipleToolCallProvider()
    engine = ReviewEngine(GitHubService(settings, client), provider, settings)

    with caplog.at_level("INFO", logger="app.services.review_service"):
        result = await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))

    assert result.status == "completed"
    assert "finish_reason=None" in caplog.text
    assert "tool_call_count=2" in caplog.text
    assert "content_chars=0" in caplog.text
    assert "app.py" not in caplog.text
    await client.aclose()


@pytest.mark.parametrize("finish_reason", ["stop", "length"])
@pytest.mark.asyncio
async def test_empty_final_response_reports_finish_reason(caplog, finish_reason) -> None:
    settings = make_settings()
    client = make_client()
    provider = SingleResponseProvider(
        AIMessage(content="", response_metadata={"finish_reason": finish_reason})
    )
    engine = ReviewEngine(GitHubService(settings, client), provider, settings)

    with caplog.at_level("INFO", logger="app.services.review_service"):
        with pytest.raises(ReviewOutputError, match="final response was empty"):
            await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))

    assert f"finish_reason={finish_reason}" in caplog.text
    assert "tool_call_count=0" in caplog.text
    assert "content_chars=0" in caplog.text
    assert "max_output_tokens=2048" in caplog.text
    await client.aclose()


@pytest.mark.asyncio
async def test_agent_rejects_finding_for_line_outside_diff() -> None:
    invalid = json.dumps(
        {
            "summary": "Invalid evidence",
            "findings": [
                {
                    "file_path": "app.py",
                    "line_start": 99,
                    "line_end": 99,
                    "severity": "high",
                    "category": "bug",
                    "title": "Unsupported claim",
                    "explanation": "No evidence.",
                    "evidence": "No evidence.",
                    "suggested_fix": "Investigate.",
                    "certainty": "speculative",
                }
            ],
        }
    )
    settings = make_settings()
    client = make_client()
    engine = ReviewEngine(GitHubService(settings, client), FakeProvider(invalid), settings)

    with pytest.raises(Exception, match="outside the available diff"):
        await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))
    await client.aclose()


@pytest.mark.asyncio
async def test_agent_returns_limited_result_at_tool_call_budget() -> None:
    settings = make_settings(ai_max_tool_calls=1)
    client = make_client()
    engine = ReviewEngine(GitHubService(settings, client), FakeProvider(), settings)

    result = await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))

    assert result.status == "limited"
    assert result.stop_reason == "maximum_tool_calls"
    assert result.tool_calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_agent_reports_malformed_final_output() -> None:
    settings = make_settings()
    client = make_client()
    engine = ReviewEngine(GitHubService(settings, client), FakeProvider("not json"), settings)

    with pytest.raises(ReviewOutputError, match="valid review JSON"):
        await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))
    await client.aclose()


@pytest.mark.asyncio
async def test_agent_rejects_empty_final_output() -> None:
    settings = make_settings()
    client = make_client()
    engine = ReviewEngine(GitHubService(settings, client), FakeProvider(""), settings)

    with pytest.raises(ReviewOutputError, match="final response was empty"):
        await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))
    await client.aclose()


@pytest.mark.asyncio
async def test_agent_returns_controlled_limited_result_when_iterations_exhausted() -> None:
    settings = make_settings(ai_max_iterations=1)
    client = make_client()
    provider = FakeProvider()
    engine = ReviewEngine(GitHubService(settings, client), provider, settings)

    result = await engine.review(PullRequestRequest(url="https://github.com/example/repo/pull/1"))

    assert result.status == "limited"
    assert result.stop_reason == "maximum_iterations"
    assert result.review.findings == []
    assert result.iterations == 1
    assert provider.calls == 1
    await client.aclose()

