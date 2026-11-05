import httpx
import pytest

from app.core.config import Settings
from app.services.github_service import GitHubAPIError, GitHubRateLimitError, GitHubService
from app.services.github_url import parse_github_pr_url


def settings(**overrides) -> Settings:
    return Settings(github_api_base_url="https://api.github.test", **overrides)


def metadata_payload() -> dict:
    return {
        "title": "Improve auth",
        "body": "Please review",
        "state": "open",
        "html_url": "https://github.com/example/repo/pull/1",
        "user": {"login": "developer"},
        "base": {"ref": "main", "sha": "base-sha"},
        "head": {"ref": "feature", "sha": "head-sha"},
    }


def file_payload(filename: str, patch: str | None) -> dict:
    return {
        "filename": filename,
        "status": "modified",
        "additions": 1,
        "deletions": 0,
        "changes": 1,
        **({"patch": patch} if patch is not None else {}),
    }


@pytest.mark.asyncio
async def test_fetches_metadata_and_changed_files_with_missing_patch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/1"):
            return httpx.Response(200, json=metadata_payload())
        return httpx.Response(
            200,
            json=[file_payload("src/auth.py", "@@ -1 +1 @@\n-old\n+new") , file_payload("image.png", None)],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://api.github.test", transport=transport) as client:
        service = GitHubService(settings(), client)
        result = await service.fetch_pull_request(parse_github_pr_url("https://github.com/example/repo/pull/1"))

    assert result.metadata.title == "Improve auth"
    assert len(result.changed_files) == 2
    assert result.changed_files[0].patch_available is True
    assert result.changed_files[1].patch_available is False


@pytest.mark.asyncio
async def test_follows_next_link_for_pagination() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/pulls/1"):
            return httpx.Response(200, json=metadata_payload())
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[file_payload("one.py", "@@ -1 +1 @@")],
                headers={"link": '<https://api.github.test/repos/example/repo/pulls/1/files?per_page=100&page=2>; rel="next"'},
            )
        return httpx.Response(200, json=[file_payload("two.py", "@@ -1 +1 @@")])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://api.github.test", transport=transport) as client:
        service = GitHubService(settings(), client)
        result = await service.fetch_pull_request(parse_github_pr_url("https://github.com/example/repo/pull/1"))

    assert [item.path for item in result.changed_files] == ["one.py", "two.py"]
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_rate_limit_is_distinguished() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"}, headers={"x-ratelimit-remaining": "0"})

    async with httpx.AsyncClient(base_url="https://api.github.test", transport=httpx.MockTransport(handler)) as client:
        service = GitHubService(settings(), client)
        with pytest.raises(GitHubRateLimitError):
            await service.fetch_pull_request(parse_github_pr_url("https://github.com/example/repo/pull/1"))


@pytest.mark.asyncio
async def test_api_error_preserves_status_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    async with httpx.AsyncClient(base_url="https://api.github.test", transport=httpx.MockTransport(handler)) as client:
        service = GitHubService(settings(), client)
        with pytest.raises(GitHubAPIError) as error:
            await service.fetch_pull_request(parse_github_pr_url("https://github.com/example/repo/pull/1"))
    assert error.value.status_code == 404

