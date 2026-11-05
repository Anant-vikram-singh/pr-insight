from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.github import PullRequestRequest

Severity = Literal["critical", "high", "medium", "low"]
FindingCategory = Literal[
    "bug",
    "security",
    "performance",
    "maintainability",
    "testing",
    "style",
]
FindingCertainty = Literal["evidence_backed", "speculative"]


class FindingCandidate(BaseModel):
    file_path: str = Field(min_length=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    severity: Severity
    category: FindingCategory
    title: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    suggested_fix: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    certainty: FindingCertainty

    @model_validator(mode="after")
    def validate_line_range(self):
        if self.line_start is None and self.line_end is not None:
            raise ValueError("line_end requires line_start")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ReviewResponse(BaseModel):
    summary: str = Field(min_length=1)
    findings: list[FindingCandidate] = Field(default_factory=list)
    test_suggestions: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    request: PullRequestRequest
    review: ReviewResponse
    status: Literal["completed", "limited"]
    tool_calls: int = Field(ge=0)
    iterations: int = Field(ge=0)
    stop_reason: str


class TestSuggestionInput(BaseModel):
    file_path: str = Field(min_length=1)
    focus: str = Field(default="behavior changed by this pull request", min_length=1, max_length=500)


class FileDiffInput(BaseModel):
    file_path: str = Field(min_length=1)

