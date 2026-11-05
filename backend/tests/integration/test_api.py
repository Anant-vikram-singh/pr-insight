import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.github_service import GitHubService


def test_health_endpoint() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inspection_endpoint_with_mocked_github() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/1"):
            return httpx.Response(
                200,
                json={
                    "title": "Add endpoint",
                    "body": None,
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
                    "additions": 2,
                    "deletions": 0,
                    "changes": 2,
                    "patch": "@@ -0,0 +1,2 @@\n+def endpoint():\n+    return True",
                }
            ],
        )

    settings = Settings(github_api_base_url="https://api.github.test")
    app = create_app(settings)
    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        service = GitHubService(settings, httpx.AsyncClient(base_url=settings.github_api_base_url, transport=transport))
        app.state.github_service = service
        response = client.post(
            "/api/github/pull-request/inspect",
            json={"url": "https://github.com/example/repo/pull/1"},
        )

    assert response.status_code == 200
    assert response.json()["metadata"]["title"] == "Add endpoint"
    assert response.json()["changed_files"][0]["path"] == "app.py"


@pytest.mark.parametrize("url", ["https://example.com/a/b/pull/1", "https://github.com/a/b/issues/1"])
def test_inspection_endpoint_rejects_invalid_url(url: str) -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/github/pull-request/inspect", json={"url": url})
    assert response.status_code == 400

