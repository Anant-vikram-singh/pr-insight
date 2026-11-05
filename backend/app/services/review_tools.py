import json
import re
from dataclasses import dataclass

from langchain_core.tools import BaseTool, StructuredTool

from app.schemas.github import PullRequestInspection
from app.schemas.review import FileDiffInput, TestSuggestionInput
from app.services.github_service import GitHubService
from app.services.github_url import parse_github_pr_url


@dataclass
class ReviewToolContext:
    github_service: GitHubService
    pr_url: str
    inspection: PullRequestInspection | None = None
    max_tool_result_chars: int = 12_000

    async def get_inspection(self) -> PullRequestInspection:
        if self.inspection is None:
            reference = parse_github_pr_url(self.pr_url)
            self.inspection = await self.github_service.fetch_pull_request(reference)
        return self.inspection


def _json(value) -> str:
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)


def _changed_function(patch: str | None) -> str | None:
    if not patch:
        return None
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            match = re.search(r"(?:async\s+)?def\s+([A-Za-z_]\w*)", line)
            if match:
                return match.group(1)
    for line in patch.splitlines():
        if line.startswith("@@"):
            context = line.split("@@", 2)[-1]
            match = re.search(r"(?:async\s+)?def\s+([A-Za-z_]\w*)", context)
            if match:
                return match.group(1)
    return None


def _test_suggestions_for_diff(file_path: str, patch: str | None, focus: str) -> dict[str, object]:
    if not patch:
        return {
            "file_path": file_path,
            "changed_function": None,
            "behavior": None,
            "focus": focus,
            "suggestions": [],
            "reason": "No patch is available, so grounded test suggestions cannot be generated.",
        }
    changed_function = _changed_function(patch)
    function_label = f"`{changed_function}()`" if changed_function else f"the change in `{file_path}`"
    diff_text = patch or ""
    lowered = diff_text.lower()

    if any(term in lowered for term in ("stat.s_irusr", "stat.s_iwusr", "permission", "chmod", "mode=")):
        behavior = f"{function_label} creates the copied destination with owner read/write permissions before source metadata is applied."
        suggestions = [
            f"On POSIX, force the cross-filesystem fallback for {function_label} (make rename raise EXDEV) and assert the destination stays owner-readable and owner-writable only (0o600) while bytes are being written.",
            f"Run {function_label} with private source modes 0o600 and 0o640, then assert the completed destination matches each source mode, preserves the file contents, and removes the source after a successful copy.",
            f"With an existing destination and allow_overwrite=True, verify the copy replaces its contents without broadening its existing permissions; this checks the changed creation mode is applied only when a destination is newly created.",
        ]
        return {
            "file_path": file_path,
            "changed_function": changed_function,
            "behavior": behavior,
            "focus": focus,
            "suggestions": suggestions,
        }

    behavior = f"the changed behavior in `{file_path}`"
    if changed_function:
        behavior = f"{function_label} as changed in the diff"
    return {
        "file_path": file_path,
        "changed_function": changed_function,
        "behavior": behavior,
        "focus": focus,
        "suggestions": [
            f"Add a regression test for {behavior} that asserts the concrete output or state changed by the added lines.",
            f"Exercise the changed branch in {behavior} and assert the failure or exception behavior shown by the surrounding diff, if that branch is reached.",
        ],
    }


def create_review_tools(context: ReviewToolContext) -> list[BaseTool]:
    async def fetch_pr_metadata() -> str:
        inspection = await context.get_inspection()
        metadata = inspection.metadata.model_copy(
            update={"description": (inspection.metadata.description or "")[:2000]}
        )
        return _json(metadata)

    async def fetch_changed_files() -> str:
        inspection = await context.get_inspection()
        files = [
            {
                "path": item.path,
                "previous_path": item.previous_path,
                "status": item.status,
                "additions": item.additions,
                "deletions": item.deletions,
                "changes": item.changes,
                "patch_available": item.patch_available,
            }
            for item in inspection.changed_files
        ]
        result = {
            "files": files,
            "files_truncated": inspection.files_truncated,
            "returned_files_truncated": False,
        }
        while len(files) > 1 and len(json.dumps(result, ensure_ascii=False)) > context.max_tool_result_chars:
            files.pop()
            result["returned_files_truncated"] = True
        return json.dumps(result, ensure_ascii=False)

    async def inspect_file_diff(file_path: str) -> str:
        arguments = FileDiffInput(file_path=file_path)
        inspection = await context.get_inspection()
        changed_file = next(
            (item for item in inspection.changed_files if item.path == arguments.file_path), None
        )
        if changed_file is None:
            raise ValueError("file_path is not part of the pull request changed files")
        patch = changed_file.patch
        if patch is not None and len(patch) > context.max_tool_result_chars:
            patch = patch[: context.max_tool_result_chars]
        return json.dumps(
            {
                **changed_file.model_dump(mode="json", exclude={"patch"}),
                "patch": patch,
                "patch_truncated": changed_file.patch is not None and len(changed_file.patch) > context.max_tool_result_chars,
            },
            ensure_ascii=False,
        )

    async def generate_test_suggestions(file_path: str, focus: str) -> str:
        arguments = TestSuggestionInput(file_path=file_path, focus=focus)
        inspection = await context.get_inspection()
        changed_file = next(
            (item for item in inspection.changed_files if item.path == arguments.file_path), None
        )
        if changed_file is None:
            raise ValueError("file_path is not part of the pull request changed files")
        result = _test_suggestions_for_diff(
            arguments.file_path,
            changed_file.patch,
            arguments.focus,
        )
        return json.dumps(result, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            coroutine=fetch_pr_metadata,
            name="fetch_pr_metadata",
            description="Fetch normalized metadata for the target pull request. Read-only; takes no arguments.",
        ),
        StructuredTool.from_function(
            coroutine=fetch_changed_files,
            name="fetch_changed_files",
            description="Fetch the normalized list of changed files and patch availability. Read-only; takes no arguments.",
        ),
        StructuredTool.from_function(
            coroutine=inspect_file_diff,
            name="inspect_file_diff",
            description="Inspect the diff for one path from the changed-file list. The path must be changed by this PR.",
            args_schema=FileDiffInput,
        ),
        StructuredTool.from_function(
            coroutine=generate_test_suggestions,
            name="generate_test_suggestions",
            description="Generate read-only test ideas for one changed file. Does not write or run tests.",
            args_schema=TestSuggestionInput,
        ),
    ]

