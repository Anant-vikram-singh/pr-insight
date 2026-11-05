import json
from datetime import datetime, timezone

import pytest

from app.schemas.github import ChangedFile, PullRequestInspection, PullRequestMetadata
from app.services.review_tools import ReviewToolContext, create_review_tools


def make_inspection(patch: str | None) -> PullRequestInspection:
    return PullRequestInspection(
        metadata=PullRequestMetadata(
            owner="django",
            repository="django",
            pull_number=22183,
            title="Restricted destination permissions",
            description=None,
            state="open",
            author="sarahboyce",
            html_url="https://github.com/django/django/pull/22183",
            base_branch="main",
            head_branch="permissions-during-move",
            base_sha="base",
            head_sha="head",
        ),
        changed_files=[
            ChangedFile(
                path="django/core/files/move.py",
                status="modified",
                additions=5,
                deletions=0,
                changes=5,
                patch=patch,
                patch_available=patch is not None,
            )
        ],
        retrieved_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_test_suggestions_are_grounded_in_permission_diff() -> None:
    patch = """@@ -6,6 +6,7 @@ def file_move_safe(
 import os
+import stat
@@ -58,6 +59,10 @@ def file_move_safe(
             mode=stat.S_IRUSR | stat.S_IWUSR,
"""
    context = ReviewToolContext(
        github_service=None,  # type: ignore[arg-type]
        pr_url="https://github.com/django/django/pull/22183",
        inspection=make_inspection(patch),
    )
    tool = next(tool for tool in create_review_tools(context) if tool.name == "generate_test_suggestions")

    result = json.loads(await tool.ainvoke({
        "file_path": "django/core/files/move.py",
        "focus": "permission handling during fallback copying",
    }))

    assert result["changed_function"] == "file_move_safe"
    assert "EXDEV" in result["suggestions"][0]
    assert "0o600" in result["suggestions"][0]
    assert "allow_overwrite=True" in result["suggestions"][2]
    assert all("normal path" not in suggestion.lower() for suggestion in result["suggestions"])


@pytest.mark.asyncio
async def test_test_suggestions_are_empty_when_patch_is_unavailable() -> None:
    context = ReviewToolContext(
        github_service=None,  # type: ignore[arg-type]
        pr_url="https://github.com/django/django/pull/22183",
        inspection=make_inspection(None),
    )
    tool = next(tool for tool in create_review_tools(context) if tool.name == "generate_test_suggestions")

    result = json.loads(await tool.ainvoke({
        "file_path": "django/core/files/move.py",
        "focus": "permission handling",
    }))

    assert result["suggestions"] == []
    assert "No patch is available" in result["reason"]
