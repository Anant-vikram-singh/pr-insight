import logging

from fastapi import APIRouter, HTTPException, Request

from app.schemas.github import PullRequestInspection, PullRequestRequest
from app.schemas.review import ReviewResult
from app.services.github_service import GitHubAPIError, GitHubRateLimitError
from app.services.llm_provider import LLMProviderError
from app.services.review_service import EvidenceValidationError, ReviewEngineError, ReviewOutputError
from app.services.github_url import InvalidGitHubPRUrl, parse_github_pr_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/reviews", response_model=ReviewResult)
async def create_review(payload: PullRequestRequest, request: Request) -> ReviewResult:
    try:
        return await request.app.state.review_engine.review(payload)
    except InvalidGitHubPRUrl as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ReviewOutputError, EvidenceValidationError) as exc:
        logger.exception("Review response validation failed; error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (LLMProviderError, ReviewEngineError) as exc:
        logger.exception("Review request failed; error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        logger.exception("Review GitHub rate limit failure")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubAPIError as exc:
        logger.exception("Review GitHub API failure; status_code=%s", exc.status_code)
        status_code = 404 if exc.status_code == 404 else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/github/pull-request/inspect", response_model=PullRequestInspection)
async def inspect_pull_request(
    payload: PullRequestRequest, request: Request
) -> PullRequestInspection:
    try:
        reference = parse_github_pr_url(str(payload.url))
        service = request.app.state.github_service
        return await service.fetch_pull_request(reference)
    except InvalidGitHubPRUrl as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubAPIError as exc:
        status_code = 404 if exc.status_code == 404 else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

