import os
import json
from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from yaxai.cli import DEFAULT_CATALOG_CONFIG_FILENAME, DEFAULT_CONFIG_FILENAME, app


runner = CliRunner()


def test_agentsmd_build_missing_config():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["agentsmd", "build"])

    assert result.exit_code == 1
    assert "Configuration file not found" in result.stdout


def test_agentsmd_build_uses_parent_fallback_config():
    with runner.isolated_filesystem():
        root_dir = Path.cwd()
        project_dir = root_dir / "fooproject"
        project_dir.mkdir()

        fallback_path = root_dir / f"{project_dir.name}-{DEFAULT_CONFIG_FILENAME}"
        fallback_path.write_text(
            dedent(
                """
                build:
                  agentsmd:
                    from:
                      - https://github.com/hekonsek/yax/blob/main/README.md
                """
            ),
            encoding="utf-8",
        )

        original_cwd = Path.cwd()
        try:
            os.chdir(project_dir)
            result = runner.invoke(app, ["agentsmd", "build"])
        finally:
            os.chdir(original_cwd)

        output_path = project_dir / "AGENTS.md"

        assert result.exit_code == 0
        assert output_path.exists()
        assert "# yax: You Are eXpert" in output_path.read_text(encoding="utf-8")
        assert f"Using fallback configuration file: {fallback_path}" in result.stdout
        assert "Generated agents markdown: " in result.stdout


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


def test_agentsmd_build_uses_config_and_builds_output():
    with runner.isolated_filesystem():
        Path(DEFAULT_CONFIG_FILENAME).write_text(
            dedent(
                """
                build:
                  agentsmd:
                    from:
                      - https://github.com/hekonsek/yax/blob/main/README.md
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["agentsmd", "build"])

        output_path = Path("AGENTS.md")

        assert result.exit_code == 0
        assert "Generated agents markdown: " in result.stdout
        assert "# yax: You Are eXpert" in output_path.read_text(encoding="utf-8")


def test_agentsmd_build_honors_output_override():
    with runner.isolated_filesystem():
        Path(DEFAULT_CONFIG_FILENAME).write_text(
            dedent(
                """
                build:
                  agentsmd:
                    from:
                      - https://github.com/hekonsek/yax/blob/main/README.md
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["agentsmd", "build", "--output", "docs/output.md"])

        output_path = Path("docs/output.md")

        assert result.exit_code == 0
        assert output_path.exists()
        assert "# yax: You Are eXpert" in output_path.read_text(encoding="utf-8")
        assert "Generated agents markdown: " in result.stdout


def test_root_build_alias_runs_agentsmd_workflow():
    with runner.isolated_filesystem():
        Path(DEFAULT_CONFIG_FILENAME).write_text(
            dedent(
                """
                build:
                  agentsmd:
                    from:
                      - https://github.com/hekonsek/yax/blob/main/README.md
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["build"])

        output_path = Path("AGENTS.md")

        assert result.exit_code == 0
        assert "# yax: You Are eXpert" in output_path.read_text(encoding="utf-8")
        assert "Generated agents markdown: " in result.stdout


def test_catalog_build_missing_config():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["catalog", "build"])

    assert result.exit_code == 1
    assert "Configuration file not found" in result.stdout


def test_catalog_build_creates_json():
    with runner.isolated_filesystem():
        Path("source.yml").write_text(
            dedent(
                """
                build:
                  agentsmd:
                    metadata:
                      name: Example Catalog
                """
            ),
            encoding="utf-8",
        )
        Path(DEFAULT_CATALOG_CONFIG_FILENAME).write_text(
            dedent(
                """
                build:
                  catalog:
                    organization: example
                    from:
                      - file:source.yml
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["catalog", "build"])

        output_path = Path("yax-catalog.json")

        assert result.exit_code == 0
        assert output_path.exists()
        assert "Generated catalog" in result.stdout


def test_catalog_build_honors_output_override():
    with runner.isolated_filesystem():
        Path(DEFAULT_CATALOG_CONFIG_FILENAME).write_text(
            dedent(
                """
                build:
                  catalog:
                    organization: example
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["catalog", "build", "--output", "dist/catalog.json"])

        output_path = Path("dist/catalog.json")

        assert result.exit_code == 0
        assert output_path.exists()
        assert "Generated catalog" in result.stdout


def test_catalog_export_missing_source():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["catalog", "export"])

    assert result.exit_code == 1
    assert "Catalog source file not found" in result.stdout


def test_catalog_export_writes_markdown():
    catalog_data = {
        "organizations": [
            {
                "name": "Example",
                "collections": [{"url": "https://example.com/catalog.yml"}],
            }
        ]
    }

    with runner.isolated_filesystem():
        Path("yax-catalog.json").write_text(
            json.dumps(catalog_data),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["catalog", "export"])

        output_path = Path("yax-catalog.md")

        assert result.exit_code == 0
        assert output_path.read_text(encoding="utf-8") == (
            "# Catalog\n\n## Example\n\n- https://example.com/catalog.yml\n"
        )
        assert "Exported catalog" in result.stdout


def test_catalog_export_reports_unsupported_format():
    catalog_data = {
        "organizations": [
            {
                "name": "Example",
                "collections": [{"url": "https://example.com/catalog.yml"}],
            }
        ]
    }

    with runner.isolated_filesystem():
        Path("yax-catalog.json").write_text(
            json.dumps(catalog_data),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["catalog", "export", "--format", "txt"])

        assert result.exit_code == 1
        assert "Unsupported export format" in result.stdout
