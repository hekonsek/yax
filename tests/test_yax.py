import json
from pathlib import Path
from textwrap import dedent

import pytest

from yaxai.yax import (
    AgentsmdBuildConfig,
    CatalogBuildConfig,
    CatalogSource,
    CatalogCollection,
    DEFAULT_AGENTSMD_OUTPUT,
    DEFAULT_CATALOG_OUTPUT,
    Discovery,
    Yax,
)


def _write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "config.yml"
    config_path.write_text(dedent(contents), encoding="utf-8")
    return config_path


def test_catalog_collection_output_url_replaces_filename():
    collection = CatalogCollection(
        url="https://example.com/path/to/yax.yml",
        output="AGENTS.md",
    )

    assert collection.output_url() == "https://example.com/path/to/AGENTS.md"


def test_catalog_collection_output_url_preserves_query_and_fragment():
    collection = CatalogCollection(
        url="https://example.com/path/yax-export.yml?raw=1#section",
        output="docs/catalog.md",
    )

    assert collection.output_url() == "https://example.com/path/catalog.md?raw=1#section"


def test_catalog_collection_output_url_defaults_to_agents_md():
    collection = CatalogCollection(url="https://example.com/path/yax.yml")

    assert collection.output_url() == "https://example.com/path/_agents.md"


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
    assert [source.url for source in config.sources] == [
        "https://example.com/first.yml",
        "https://example.com/second.yml",
    ]
    assert config.output == "generated/catalog.json"


def test_open_catalog_build_config_rejects_name(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog:
            organization: example
            from:
              - url: https://example.com/catalog.yml
                name: Example Catalog
        """,
    )

    with pytest.raises(ValueError, match=r"'name' is no longer supported"):
        CatalogBuildConfig.open_catalog_build_config(str(config_file))


def test_open_catalog_build_config_rejects_metadata(tmp_path):
    config_file = _write_config(
        tmp_path,
        """
        build:
          catalog:
            organization: example
            from:
              - url: https://example.com/catalog.yml
                metadata:
                  name: Example Catalog
        """,
    )

    with pytest.raises(ValueError, match=r"'metadata' is no longer supported"):
        CatalogBuildConfig.open_catalog_build_config(str(config_file))


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
    source_path = tmp_path / "source.yml"
    source_path.write_text("", encoding="utf-8")
    config = CatalogBuildConfig(
        organization="example",
        sources=["file:" + str(source_path)],
        output=str(output_path),
    )

    Yax().build_catalog(config)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    assert result == {
        "organizations": [
            {
                "collections": [{"url": "file:" + str(source_path)}],
                "name": "example",
            }
        ]
    }


def test_build_catalog_includes_metadata(tmp_path):
    output_path = tmp_path / "dir" / "catalog.json"
    source_path = tmp_path / "source.yml"
    source_path.write_text(
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
    config = CatalogBuildConfig(
        organization="example",
        sources=[CatalogSource(url="file:" + str(source_path))],
        output=str(output_path),
    )

    Yax().build_catalog(config)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    expected_collection = {
        "url": "file:" + str(source_path),
        "name": "Example Catalog",
        "output": DEFAULT_AGENTSMD_OUTPUT,
    }

    assert result == {
        "organizations": [
            {
                "collections": [expected_collection],
                "name": "example",
            }
        ]
    }


def test_build_catalog_reads_output_from_source(tmp_path):
    output_path = tmp_path / "dir" / "catalog.json"
    source_path = tmp_path / "source.yml"
    source_path.write_text(
        dedent(
            """
            build:
              agentsmd:
                output: docs/catalog.md
            """
        ),
        encoding="utf-8",
    )
    config = CatalogBuildConfig(
        organization="example",
        sources=[CatalogSource(url="file:" + str(source_path))],
        output=str(output_path),
    )

    Yax().build_catalog(config)

    result = json.loads(output_path.read_text(encoding="utf-8"))

    expected_collection = {
        "url": "file:" + str(source_path),
        "output": "docs/catalog.md",
    }

    assert result == {
        "organizations": [
            {
                "collections": [expected_collection],
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


def test_export_catalog_markdown_uses_metadata_name(tmp_path):
    source = tmp_path / "catalog.json"
    catalog_data = {
        "organizations": [
            {
                "name": "Example Org",
                "collections": [
                    {"url": "https://example.com/one.yml", "name": "Example Catalog"}
                ],
            }
        ]
    }
    source.write_text(json.dumps(catalog_data), encoding="utf-8")

    output_path = Yax().export_catalog(source, "markdown")

    assert output_path.read_text(encoding="utf-8") == (
        "# Catalog\n\n## Example Org\n\n- [Example Catalog](https://example.com/one.yml)\n"
    )


def test_export_catalog_markdown_supports_legacy_metadata(tmp_path):
    source = tmp_path / "catalog.json"
    catalog_data = {
        "organizations": [
            {
                "name": "Example Org",
                "collections": [
                    {
                        "url": "https://example.com/one.yml",
                        "metadata": {"name": "Legacy Catalog"},
                    }
                ],
            }
        ]
    }
    source.write_text(json.dumps(catalog_data), encoding="utf-8")

    output_path = Yax().export_catalog(source, "markdown")

    assert output_path.read_text(encoding="utf-8") == (
        "# Catalog\n\n## Example Org\n\n- [Legacy Catalog](https://example.com/one.yml)\n"
    )


def test_agentsmd_build_config_parses_metadata(tmp_path):
    config_path = tmp_path / "yax.yml"
    config_path.write_text(
        dedent(
            """
            build:
              agentsmd:
                from:
                  - https://example.com/agents.md
                metadata:
                  name: Example Project
            """
        ),
        encoding="utf-8",
    )

    config = AgentsmdBuildConfig.parse_yml(config_path)

    assert config.urls == ["https://example.com/agents.md"]
    assert config.metadata.get("name") == "Example Project"


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


def test_discovery_returns_collections(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "organizations": [
                    {
                        "name": "Example Org",
                        "collections": [
                            {"url": "https://example.com/one.yml", "name": "Example One"},
                            {"url": "https://example.com/two.yml"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    collections = Discovery(catalog_path).discover()

    assert len(collections) == 2
    assert collections[0].url == "https://example.com/one.yml"
    assert collections[0].name == "Example One"
    assert collections[1].url == "https://example.com/two.yml"
    assert collections[1].name is None


def test_discovery_missing_file(tmp_path):
    discovery = Discovery(tmp_path / "missing.json")

    with pytest.raises(FileNotFoundError):
        discovery.discover()


def test_discovery_invalid_json(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("not json", encoding="utf-8")

    discovery = Discovery(catalog_path)

    with pytest.raises(ValueError):
        discovery.discover()
