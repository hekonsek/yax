from pathlib import Path
from textwrap import dedent

import pytest

from urllib.error import URLError

from yaxai.yax import AgentsmdBuildConfig, DEFAULT_AGENTSMD_OUTPUT, Yax


def _write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "config.yml"
    config_path.write_text(dedent(contents), encoding="utf-8")
    return config_path


def test_open_agentsmd_build_config_defaults(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from:
              - https://example.com/source.md
        """,
    )

    config = AgentsmdBuildConfig.open_agentsmd_build_config(config_file)

    assert config.urls is not None
    assert len(config.urls) == 1
    assert config.output == DEFAULT_AGENTSMD_OUTPUT


def test_open_agentsmd_build_config_with_urls_and_output(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from:
              - https://example.com/a.md
              - https://example.com/b.md
            output: docs/AGENTS.md
        """,
    )

    config = AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))

    assert config.urls == ["https://example.com/a.md", "https://example.com/b.md"]
    assert config.output == "docs/AGENTS.md"


def test_open_agentsmd_build_config_treats_none_output_as_default(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from:
              - https://example.com/a.md
            output: null
        """,
    )

    config = AgentsmdBuildConfig.open_agentsmd_build_config(config_file)

    assert config.output == DEFAULT_AGENTSMD_OUTPUT


def test_open_agentsmd_build_config_rejects_non_string_output(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            output:
              unexpected: value
        """,
    )

    with pytest.raises(ValueError):
        AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))


def test_open_agentsmd_build_config_requires_urls_list(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from: not-a-list
        """,
    )

    with pytest.raises(ValueError):
        AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))


def test_open_agentsmd_build_config_requires_string_urls(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from:
              - 123
        """,
    )

    with pytest.raises(ValueError):
        AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))

def test_open_agentsmd_build_config_rejects_empty_urls(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from: []
        """,
    )

    with pytest.raises(ValueError):
        AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))

def test_open_agentsmd_build_config_rejects_blank_urls(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          agentsmd:
            from:
              - "  "
        """,
    )

    with pytest.raises(ValueError):
        AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))


def test_build_agentsmd_writes_combined_content(tmp_path, monkeypatch):
    url_contents = {
        "https://example.com/first.md": "first content",
        "https://example.com/second.md": "second content",
    }

    def fake_urlopen(url):
        class _Response:
            def __init__(self, data: str):
                self._data = data.encode("utf-8")

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Response(url_contents[url])

    monkeypatch.setattr("yaxai.yax.urlopen", fake_urlopen)

    output_path = tmp_path / "generated" / "AGENTS.md"
    config = AgentsmdBuildConfig(urls=list(url_contents.keys()), output=str(output_path))

    Yax().build_agentsmd(config)

    assert Path(config.output) == output_path
    assert output_path.read_text(encoding="utf-8") == "first content\n\nsecond content"


def test_build_agentsmd_supports_local_file_sources(tmp_path, monkeypatch):
    fragments_dir = tmp_path / "fragments"
    fragments_dir.mkdir()

    first = fragments_dir / "a.md"
    second = fragments_dir / "b.md"
    first.write_text("first file", encoding="utf-8")
    second.write_text("second file", encoding="utf-8")

    config_file = _write_config(
        tmp_path,
        f"""
        build:
          agentsmd:
            from:
              - "file:fragments/a.md"
              - "file:fragments/b.md"
            output: {tmp_path / "combined.md"}
        """,
    )

    config = AgentsmdBuildConfig.open_agentsmd_build_config(str(config_file))

    monkeypatch.chdir(tmp_path)
    Yax().build_agentsmd(config)

    output_path = Path(config.output)
    assert output_path.read_text(encoding="utf-8") == "first file\n\nsecond file"


def test_build_agentsmd_glob_expands_and_sorts_matches(tmp_path, monkeypatch):
    fragments_dir = tmp_path / "fragments"
    (fragments_dir / "nested").mkdir(parents=True)

    files = {
        fragments_dir / "nested" / "c.md": "third",
        fragments_dir / "b.md": "second",
        fragments_dir / "a.md": "first",
    }

    for path, contents in files.items():
        path.write_text(contents, encoding="utf-8")

    config = AgentsmdBuildConfig(
        urls=["file:fragments/**/*.md"],
        output=str(tmp_path / "combined.md"),
    )

    monkeypatch.chdir(tmp_path)
    Yax().build_agentsmd(config)

    combined = Path(config.output).read_text(encoding="utf-8")
    assert combined == "first\n\nsecond\n\nthird"


def test_build_agentsmd_errors_when_glob_matches_nothing(tmp_path, monkeypatch):
    config = AgentsmdBuildConfig(
        urls=["file:missing.md"],
        output=str(tmp_path / "out.md"),
    )

    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        Yax().build_agentsmd(config)


def test_build_agentsmd_wraps_url_errors(tmp_path, monkeypatch):
    failing_url = "https://example.com/failure.md"

    def fake_urlopen(url):
        raise URLError("boom")

    monkeypatch.setattr("yaxai.yax.urlopen", fake_urlopen)

    config = AgentsmdBuildConfig(urls=[failing_url], output=str(tmp_path / "AGENTS.md"))

    with pytest.raises(RuntimeError) as exc:
        Yax().build_agentsmd(config)

    assert failing_url in str(exc.value)
