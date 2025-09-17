from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from yax.cli import DEFAULT_CONFIG_FILENAME, app


runner = CliRunner()


def test_agentsmd_build_missing_config():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["agentsmd", "build"])

    assert result.exit_code == 1
    assert "Configuration file not found" in result.stdout


@pytest.fixture(name="stub_urlopen")
def fixture_stub_urlopen():
    def _factory(responses):
        class _Response:
            def __init__(self, data: str):
                self._data = data.encode("utf-8")

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def _opener(url):
            return _Response(responses[url])

        return _opener

    return _factory


def test_agentsmd_build_uses_config_and_builds_output(monkeypatch, stub_urlopen):
    monkeypatch.setattr(
        "yax.yax.urlopen",
        stub_urlopen({"https://example.com/one.md": "downloaded"}),
    )

    with runner.isolated_filesystem():
        Path(DEFAULT_CONFIG_FILENAME).write_text(
            dedent(
                """
                build:
                  agentsmd:
                    from:
                      - https://example.com/one.md
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["agentsmd", "build"])

        output_path = Path("AGENTS.md")

        assert result.exit_code == 0
        assert "Loaded agentsmd build config" in result.stdout
        assert "Generated agents markdown" in result.stdout
        assert output_path.read_text(encoding="utf-8") == "downloaded"


def test_agentsmd_build_honors_output_override():
    with runner.isolated_filesystem():
        Path(DEFAULT_CONFIG_FILENAME).write_text("", encoding="utf-8")

        result = runner.invoke(app, ["agentsmd", "build", "--output", "docs/output.md"])

        output_path = Path("docs/output.md")

        assert result.exit_code == 0
        assert output_path.exists()
        assert "Generated agents markdown" in result.stdout
