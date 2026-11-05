import pytest

from app.services.github_url import InvalidGitHubPRUrl, parse_github_pr_url


def test_parse_public_pull_request_url() -> None:
    result = parse_github_pr_url("https://github.com/EricCogen/GauntletCI-Demo/pull/12")
    assert result.owner == "EricCogen"
    assert result.repository == "GauntletCI-Demo"
    assert result.pull_number == 12


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/repo/pull/1",
        "https://gitlab.com/example/repo/pull/1",
        "https://github.com/example/repo/issues/1",
        "https://github.com/example/repo/pull/not-a-number",
    ],
)
def test_reject_invalid_pull_request_urls(url: str) -> None:
    with pytest.raises(InvalidGitHubPRUrl):
        parse_github_pr_url(url)

