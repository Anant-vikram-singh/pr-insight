from urllib.parse import urlparse

from app.schemas.github import GitHubPRReference


class InvalidGitHubPRUrl(ValueError):
    """Raised when a URL is not a supported public GitHub pull request URL."""


def parse_github_pr_url(url: str) -> GitHubPRReference:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise InvalidGitHubPRUrl("URL must use https://github.com")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2].lower() != "pull":
        raise InvalidGitHubPRUrl("URL must match https://github.com/{owner}/{repo}/pull/{number}")

    owner, repository, _, number = parts
    if not owner or not repository or not number.isdigit() or int(number) <= 0:
        raise InvalidGitHubPRUrl("URL contains an invalid owner, repository, or pull request number")

    return GitHubPRReference(owner=owner, repository=repository, pull_number=int(number))

