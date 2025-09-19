import json
from pathlib import Path
from textwrap import dedent

import pytest

from yaxai.yax import CatalogBuildConfig, DEFAULT_CATALOG_OUTPUT, Yax


def _write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "config.yml"
    config_path.write_text(dedent(contents), encoding="utf-8")
    return config_path


def test_open_catalog_build_config_defaults(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog:
            organization: example
        """,
    )

    config = CatalogBuildConfig.open_catalog_build_config(str(config_file))

    assert config.organization == "example"
    assert config.sources == []
    assert config.output == DEFAULT_CATALOG_OUTPUT


def test_open_catalog_build_config_with_sources_and_output(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog:
            organization: example
            from:
              - https://example.com/first.yml
              - https://example.com/second.yml
            output: generated/catalog.json
        """,
    )

    config = CatalogBuildConfig.open_catalog_build_config(str(config_file))

    assert config.organization == "example"
    assert config.sources == [
        "https://example.com/first.yml",
        "https://example.com/second.yml",
    ]
    assert config.output == "generated/catalog.json"


def test_open_catalog_build_config_requires_org(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog: {}
        """,
    )

    with pytest.raises(ValueError):
        CatalogBuildConfig.open_catalog_build_config(str(config_file))


def test_open_catalog_build_config_requires_list_sources(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog:
            organization: example
            from: invalid
        """,
    )

    with pytest.raises(ValueError):
        CatalogBuildConfig.open_catalog_build_config(str(config_file))


def test_open_catalog_build_config_requires_string_sources(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog:
            organization: example
            from:
              - 42
        """,
    )

    with pytest.raises(ValueError):
        CatalogBuildConfig.open_catalog_build_config(str(config_file))


def test_build_catalog_writes_expected_json(tmp_path):
    output_path = tmp_path / "dir" / "catalog.json"
    config = CatalogBuildConfig(
        organization="example",
        sources=["https://example.com/catalog.yml"],
        output=str(output_path),
    )

    Yax().build_catalog(config)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    assert result == {
        "organizations": [
            {
                "collections": [{"url": "https://example.com/catalog.yml"}],
                "name": "example",
            }
        ]
    }


def test_export_catalog_writes_markdown(tmp_path):
    source = tmp_path / "catalog.json"
    catalog_data = {
        "organizations": [
            {
                "name": "Example Org",
                "collections": [
                    {"url": "https://example.com/one.yml"},
                    {"url": "https://example.com/two.yml"},
                ],
            }
        ]
    }
    source.write_text(json.dumps(catalog_data), encoding="utf-8")

    output_path = Yax().export_catalog(source, "markdown")

    assert output_path == source.with_suffix(".md")
    assert output_path.read_text(encoding="utf-8") == (
        "# Catalog\n\n## Example Org\n\n- https://example.com/one.yml\n"
        "- https://example.com/two.yml\n"
    )


def test_export_catalog_rejects_invalid_json(tmp_path):
    source = tmp_path / "catalog.json"
    source.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError):
        Yax().export_catalog(source, "markdown")


def test_export_catalog_rejects_unknown_format(tmp_path):
    source = tmp_path / "catalog.json"
    source.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        Yax().export_catalog(source, "unsupported")
