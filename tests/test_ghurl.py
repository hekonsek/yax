from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest

from yaxai.ghurl import GitHubFile


def test_parse_accepts_github_ui_url() -> None:
    instance = GitHubFile.parse("https://github.com/acme/widgets/blob/main/docs/AGENTS.md")

    assert isinstance(instance, GitHubFile)
    assert instance.url == "https://github.com/acme/widgets/blob/main/docs/AGENTS.md"
    assert urlparse(instance.url).path == "/acme/widgets/blob/main/docs/AGENTS.md"


def test_parse_accepts_www_prefixed_host() -> None:
    instance = GitHubFile.parse("https://www.github.com/acme/widgets/blob/main/README.md")

    parsed = urlparse(instance.url)
    assert parsed.netloc == "github.com"


def test_parse_accepts_github_raw_url() -> None:
    instance = GitHubFile.parse("https://raw.githubusercontent.com/acme/widgets/main/docs/AGENTS.md")

    parsed = urlparse(instance.url)
    assert parsed.netloc == "github.com"
    assert parsed.path == "/acme/widgets/blob/main/docs/AGENTS.md"
    assert instance.url == "https://github.com/acme/widgets/blob/main/docs/AGENTS.md"


def test_raw_returns_raw_url_for_ui_url() -> None:
    instance = GitHubFile.parse("https://github.com/acme/widgets/blob/main/README.md")

    assert instance.raw() == "https://raw.githubusercontent.com/acme/widgets/main/README.md"


def test_raw_returns_raw_url_for_raw_input() -> None:
    instance = GitHubFile.parse("https://raw.githubusercontent.com/acme/widgets/main/docs/AGENTS.md")

    assert instance.raw() == "https://raw.githubusercontent.com/acme/widgets/main/docs/AGENTS.md"


def test_is_visible_returns_true_for_public_file() -> None:
    instance = GitHubFile.parse("https://github.com/hekonsek/yax/blob/main/README.md")

    assert instance.is_visible()


def test_is_visible_returns_false_for_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout: float = 10.0):
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr("yaxai.ghurl.urlopen", fake_urlopen)

    instance = GitHubFile.parse("https://github.com/acme/widgets/blob/main/README.md")

    assert not instance.is_visible()


def test_is_visible_returns_false_for_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout: float = 10.0):
        raise URLError("boom")

    monkeypatch.setattr("yaxai.ghurl.urlopen", fake_urlopen)

    instance = GitHubFile.parse("https://github.com/acme/widgets/blob/main/README.md")

    assert not instance.is_visible()


def test_download_returns_content_when_visible() -> None:
    instance = GitHubFile.parse("https://github.com/hekonsek/yax/blob/main/README.md")

    content = instance.download()

    assert "You Are eXpert" in content


def test_download_raises_when_not_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = GitHubFile.parse("https://github.com/acme/widgets/blob/main/README.md")

    monkeypatch.setattr(GitHubFile, "is_visible", lambda self: False)

    with pytest.raises(RuntimeError):
        instance.download()


def test_parse_normalizes_http_to_https() -> None:
    instance = GitHubFile.parse("http://github.com/acme/widgets/blob/main/README.md")

    assert instance.url.startswith("https://")
    assert instance.url == "https://github.com/acme/widgets/blob/main/README.md"


def test_parse_rejects_non_github_hosts() -> None:
    with pytest.raises(ValueError):
        GitHubFile.parse("https://example.com/acme/widgets/blob/main/docs/AGENTS.md")


def test_parse_requires_repository_on_github_host() -> None:
    with pytest.raises(ValueError):
        GitHubFile.parse("https://github.com/acme")


def test_parse_requires_path_segments_on_raw_host() -> None:
    with pytest.raises(ValueError):
        GitHubFile.parse("https://raw.githubusercontent.com/acme/widgets/main")


def test_parse_rejects_non_string_input() -> None:
    with pytest.raises(TypeError):
        GitHubFile.parse(None)  # type: ignore[arg-type]


def test_parse_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValueError):
        GitHubFile.parse("ftp://github.com/acme/widgets/blob/main/docs/AGENTS.md")
