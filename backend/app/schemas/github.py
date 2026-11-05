from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, HttpUrl, field_validator


class PullRequestRequest(BaseModel):
    url: HttpUrl


class GitHubPRReference(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    pull_number: int = Field(gt=0)


class PullRequestMetadata(BaseModel):
    owner: str
    repository: str
    pull_number: int
    title: str
    description: str | None
    state: Literal["open", "closed"]
    author: str | None
    html_url: AnyHttpUrl
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str


class ChangedFile(BaseModel):
    path: str = Field(min_length=1)
    previous_path: str | None = None
    status: Literal["added", "modified", "removed", "renamed", "copied", "changed"]
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    changes: int = Field(ge=0)
    patch: str | None = None
    patch_available: bool

    @field_validator("patch_available")
    @classmethod
    def patch_flag_matches_content(cls, value: bool, info):
        patch = info.data.get("patch")
        if value != (patch is not None):
            raise ValueError("patch_available must match whether patch is present")
        return value


class PullRequestInspection(BaseModel):
    metadata: PullRequestMetadata
    changed_files: list[ChangedFile]
    files_truncated: bool = False
    retrieved_at: datetime

