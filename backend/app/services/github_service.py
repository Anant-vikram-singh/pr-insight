import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import Settings
from app.schemas.github import (
    ChangedFile,
    GitHubPRReference,
    PullRequestInspection,
    PullRequestMetadata,
)

_NEXT_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubRateLimitError(GitHubAPIError):
    pass


class GitHubService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.github_api_base_url.rstrip("/"),
            timeout=settings.github_timeout_seconds,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_pull_request(self, reference: GitHubPRReference) -> PullRequestInspection:
        metadata_payload = await self._request_json(
            f"/repos/{reference.owner}/{reference.repository}/pulls/{reference.pull_number}"
        )
        metadata = self._normalize_metadata(reference, metadata_payload)
        files, files_truncated = await self._fetch_changed_files(reference)
        return PullRequestInspection(
            metadata=metadata,
            changed_files=files,
            files_truncated=files_truncated,
            retrieved_at=datetime.now(timezone.utc),
        )

    async def _fetch_changed_files(
        self, reference: GitHubPRReference
    ) -> tuple[list[ChangedFile], bool]:
        files: list[ChangedFile] = []
        next_url: str | None = (
            f"/repos/{reference.owner}/{reference.repository}/pulls/{reference.pull_number}/files"
            "?per_page=100&page=1"
        )
        pages = 0
        truncated = False

        while next_url and pages < self.settings.github_max_pages:
            pages += 1
            response = await self._get_response(next_url)
            payload = self._parse_response(response)
            if not isinstance(payload, list):
                raise GitHubAPIError("GitHub returned an invalid changed-files response", response.status_code)

            for item in payload:
                if len(files) >= self.settings.github_max_files:
                    truncated = True
                    break
                files.append(self._normalize_changed_file(item))

            if truncated or len(files) >= self.settings.github_max_files:
                truncated = True
                break
            next_url = self._next_url(response.headers.get("link"))

        if next_url is not None and pages >= self.settings.github_max_pages:
            truncated = True
        return files, truncated

    async def _request_json(self, path: str) -> Any:
        response = await self._get_response(path)
        return self._parse_response(response)

    async def _get_response(self, path: str) -> httpx.Response:
        try:
            response = await self._client.get(path, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise GitHubAPIError("GitHub request timed out") from exc
        except httpx.HTTPError as exc:
            raise GitHubAPIError("GitHub request failed") from exc
        return response

    def _parse_response(self, response: httpx.Response) -> Any:
        if response.status_code in (403, 429) and (
            response.status_code == 429
            or response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise GitHubRateLimitError("GitHub API rate limit exceeded", response.status_code)
        if response.is_error:
            message = self._error_message(response)
            raise GitHubAPIError(message, response.status_code)
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise GitHubAPIError("GitHub returned invalid JSON", response.status_code) from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                return f"GitHub API error ({response.status_code}): {payload['message']}"
        except ValueError:
            pass
        return f"GitHub API error ({response.status_code})"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.settings.github_api_version,
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token.get_secret_value()}"
        return headers

    @staticmethod
    def _next_url(link_header: str | None) -> str | None:
        if not link_header:
            return None
        match = _NEXT_LINK_RE.search(link_header)
        return match.group(1) if match else None

    @staticmethod
    def _normalize_metadata(
        reference: GitHubPRReference, payload: dict[str, Any]
    ) -> PullRequestMetadata:
        base = payload.get("base") or {}
        head = payload.get("head") or {}
        user = payload.get("user") or {}
        return PullRequestMetadata(
            owner=reference.owner,
            repository=reference.repository,
            pull_number=reference.pull_number,
            title=payload.get("title", ""),
            description=payload.get("body"),
            state=payload.get("state", "closed"),
            author=user.get("login"),
            html_url=payload.get("html_url"),
            base_branch=base.get("ref", ""),
            head_branch=head.get("ref", ""),
            base_sha=base.get("sha", ""),
            head_sha=head.get("sha", ""),
        )

    @staticmethod
    def _normalize_changed_file(payload: dict[str, Any]) -> ChangedFile:
        status = payload.get("status", "modified")
        if status not in {"added", "modified", "removed", "renamed", "copied", "changed"}:
            status = "changed"
        patch = payload.get("patch")
        return ChangedFile(
            path=payload.get("filename", ""),
            previous_path=payload.get("previous_filename"),
            status=status,
            additions=payload.get("additions", 0),
            deletions=payload.get("deletions", 0),
            changes=payload.get("changes", 0),
            patch=patch if isinstance(patch, str) else None,
            patch_available=isinstance(patch, str),
        )

