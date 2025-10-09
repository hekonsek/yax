from urllib.parse import urlparse

import pytest

from yaxai.ghurl import GitHubUrl


def test_parse_accepts_github_ui_url() -> None:
    instance = GitHubUrl.parse("https://github.com/acme/widgets/blob/main/docs/AGENTS.md")

    assert isinstance(instance, GitHubUrl)
    assert instance.url == "https://github.com/acme/widgets/blob/main/docs/AGENTS.md"
    assert urlparse(instance.url).path == "/acme/widgets/blob/main/docs/AGENTS.md"


def test_parse_accepts_www_prefixed_host() -> None:
    instance = GitHubUrl.parse("https://www.github.com/acme/widgets/blob/main/README.md")

    parsed = urlparse(instance.url)
    assert parsed.netloc == "www.github.com"


def test_parse_accepts_github_raw_url() -> None:
    instance = GitHubUrl.parse("https://raw.githubusercontent.com/acme/widgets/main/docs/AGENTS.md")

    parsed = urlparse(instance.url)
    assert parsed.netloc == "raw.githubusercontent.com"
    assert parsed.path.endswith("docs/AGENTS.md")


def test_parse_rejects_non_github_hosts() -> None:
    with pytest.raises(ValueError):
        GitHubUrl.parse("https://example.com/acme/widgets/blob/main/docs/AGENTS.md")


def test_parse_requires_repository_on_github_host() -> None:
    with pytest.raises(ValueError):
        GitHubUrl.parse("https://github.com/acme")


def test_parse_requires_path_segments_on_raw_host() -> None:
    with pytest.raises(ValueError):
        GitHubUrl.parse("https://raw.githubusercontent.com/acme/widgets/main")


def test_parse_rejects_non_string_input() -> None:
    with pytest.raises(TypeError):
        GitHubUrl.parse(None)  # type: ignore[arg-type]


def test_parse_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValueError):
        GitHubUrl.parse("ftp://github.com/acme/widgets/blob/main/docs/AGENTS.md")
