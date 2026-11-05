import httpx
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.core.config import Settings
from app.main import create_app
from app.services.github_service import GitHubService
from app.services.llm_provider import LLMProviderError
from app.services.review_service import ReviewEngine


class IntegrationFakeProvider:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "fetch_changed_files", "args": {}, "id": "call-1"}])
        return AIMessage(
            content='{"summary":"No evidence-backed findings.","findings":[],"test_suggestions":[]}'
        )


class FailingProvider:
    async def ainvoke(self, messages, tools):
        raise LLMProviderError("Groq provider request failed")


def test_review_endpoint_uses_tool_calling_provider() -> None:
    settings = Settings(github_api_base_url="https://api.github.test")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/1"):
            return httpx.Response(
                200,
                json={
                    "title": "Change",
                    "body": None,
                    "state": "open",
                    "html_url": "https://github.com/example/repo/pull/1",
                    "user": {"login": "dev"},
                    "base": {"ref": "main", "sha": "base"},
                    "head": {"ref": "feature", "sha": "head"},
                },
            )
        return httpx.Response(200, json=[])

    app = create_app(settings)
    with TestClient(app) as client:
        mocked_http = httpx.AsyncClient(
            base_url=settings.github_api_base_url, transport=httpx.MockTransport(handler)
        )
        provider = IntegrationFakeProvider()
        app.state.review_engine = ReviewEngine(
            GitHubService(settings, mocked_http), provider, settings
        )
        response = client.post(
            "/api/reviews", json={"url": "https://github.com/example/repo/pull/1"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["tool_calls"] == 1
    assert provider.calls == 2


def test_review_endpoint_preserves_provider_failure_response() -> None:
    settings = Settings(github_api_base_url="https://api.github.test")
    app = create_app(settings)
    app.state.review_engine = ReviewEngine(
        GitHubService(settings), FailingProvider(), settings
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/reviews", json={"url": "https://github.com/example/repo/pull/1"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Groq provider request failed"}

