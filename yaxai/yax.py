from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from glob import glob
from pathlib import Path
from typing import Any, List, Optional
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

import yaml


DEFAULT_AGENTSMD_OUTPUT = "AGENTS.md"


@dataclass
class AgentsmdBuildConfig:
    urls: Optional[List[str]] = None
    output: str = DEFAULT_AGENTSMD_OUTPUT

    @classmethod
    def open_agentsmd_build_config(cls, config_file_path: str) -> "AgentsmdBuildConfig":
        """Load Agentsmd build configuration from YAML file."""
        with open(config_file_path, "r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}

        agentsmd_section = data.get("build", {}).get("agentsmd", {})

        urls = agentsmd_section.get("from")

        output = agentsmd_section.get("output", DEFAULT_AGENTSMD_OUTPUT)
        if output is None:
            output = DEFAULT_AGENTSMD_OUTPUT
        if not isinstance(output, str):
            raise ValueError("Expected 'output' to be a string in config file")

        if urls is None:
            return cls(output=output)

        if not isinstance(urls, list):
            raise ValueError("Expected 'urls' to be a list of strings in config file")

        normalized_urls: List[str] = []
        for url in urls:
            if not isinstance(url, str):
                raise ValueError("Expected every entry in 'urls' to be a string")
            normalized_urls.append(url)

        return cls(urls=normalized_urls, output=output)


DEFAULT_CATALOG_OUTPUT = "yax-catalog.json"


@dataclass
class CatalogBuildConfig:
    organization: str
    sources: List[str] = field(default_factory=list)
    output: str = DEFAULT_CATALOG_OUTPUT

    @classmethod
    def open_catalog_build_config(cls, config_file_path: str) -> "CatalogBuildConfig":
        """Load catalog build configuration from YAML file."""

        with open(config_file_path, "r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}

        catalog_section = data.get("build", {}).get("catalog", {})

        organization = catalog_section.get("organization")
        if not isinstance(organization, str) or not organization.strip():
            raise ValueError("Expected 'organization' to be a non-empty string in config file")
        organization = organization.strip()

        raw_sources = catalog_section.get("from", [])
        if raw_sources is None:
            raw_sources = []
        if not isinstance(raw_sources, list):
            raise ValueError("Expected 'from' to be a list of strings in config file")

        sources: List[str] = []
        for source in raw_sources:
            if not isinstance(source, str):
                raise ValueError("Expected every entry in 'from' to be a string")
            stripped = source.strip()
            if stripped:
                sources.append(stripped)

        output = catalog_section.get("output", DEFAULT_CATALOG_OUTPUT)
        if output is None:
            output = DEFAULT_CATALOG_OUTPUT
        if not isinstance(output, str):
            raise ValueError("Expected 'output' to be a string in config file")

        return cls(organization=organization, sources=sources, output=output)


@dataclass
class CatalogCollection:
    url: str

    @classmethod
    def from_mapping(cls, data: Any) -> "CatalogCollection":
        if not isinstance(data, dict):
            raise ValueError("Expected collection entry to be an object")

        url = data.get("url", "")
        if isinstance(url, str):
            return cls(url=url.strip())

        raise ValueError("Expected collection 'url' to be a string")


@dataclass
class CatalogOrganization:
    name: str
    collections: List[CatalogCollection] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Any) -> "CatalogOrganization":
        if not isinstance(data, dict):
            raise ValueError("Expected organization entry to be an object")

        name_value = data.get("name", "")
        if not isinstance(name_value, str):
            raise ValueError("Expected organization 'name' to be a string")

        collections_raw = data.get("collections", [])
        if not isinstance(collections_raw, list):
            raise ValueError("Expected organization 'collections' to be a list")

        collections = [CatalogCollection.from_mapping(entry) for entry in collections_raw]

        return cls(name=name_value.strip(), collections=collections)


@dataclass
class Catalog:
    organizations: List[CatalogOrganization] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Any) -> "Catalog":
        if not isinstance(data, dict):
            raise ValueError("Catalog JSON must be an object")

        organizations_raw = data.get("organizations", [])
        if not isinstance(organizations_raw, list):
            raise ValueError("Catalog 'organizations' must be a list")

        organizations = [CatalogOrganization.from_mapping(entry) for entry in organizations_raw]

        return cls(organizations=organizations)


class Yax:
    """Core Yax entry point placeholder."""
    def build_agentsmd(self, config: AgentsmdBuildConfig) -> None:
        """Download agent markdown fragments and concatenate them into the output file."""

        urls = config.urls or []

        fragments: List[str] = []
        for url in urls:
            if url.startswith("file:"):
                fragments.extend(self._read_local_sources(url))
                continue

            try:
                with urlopen(url) as response:
                    fragments.append(response.read().decode("utf-8"))
            except URLError as exc:  # pragma: no cover - network/IO error path
                raise RuntimeError(f"Failed to download '{url}': {exc}") from exc

        output_path = Path(config.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        combined_content = "\n\n".join(fragments)
        output_path.write_text(combined_content, encoding="utf-8")

    def build_catalog(self, config: CatalogBuildConfig) -> None:
        """Construct a catalog JSON document based on the provided configuration."""

        catalog = Catalog(
            organizations=[
                CatalogOrganization(
                    name=config.organization,
                    collections=[CatalogCollection(url=source) for source in config.sources],
                )
            ]
        )

        output_path = Path(config.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            json.dumps(asdict(catalog), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def export_catalog(self, source: Path, format_name: str) -> Path:
        """Export the catalog JSON into the requested format and return output path."""

        if not source.exists():
            raise FileNotFoundError(f"Catalog source '{source}' was not found")

        try:
            catalog_data = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid catalog JSON in '{source}': {exc}") from exc

        normalized_format = format_name.strip().lower()

        catalog = Catalog.from_mapping(catalog_data)

        if normalized_format == "markdown":
            output_path = source.with_suffix(".md")
            content = self._catalog_to_markdown(catalog)
        else:
            raise ValueError(f"Unsupported export format '{format_name}'")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

        return output_path

    def _read_local_sources(self, file_url: str) -> List[str]:
        """Read and return content fragments for file-based agents sources."""

        parsed = urlparse(file_url)
        # Accept both file:relative/path and file:///absolute/path patterns.
        pattern = unquote(parsed.path or "")

        if parsed.netloc:
            if pattern.startswith("/"):
                pattern = f"{parsed.netloc}{pattern}"
            else:
                pattern = f"{parsed.netloc}/{pattern}"

        if not pattern:
            raise RuntimeError(f"File source '{file_url}' does not specify a path")

        if pattern.startswith("/"):
            glob_pattern = pattern
        else:
            glob_pattern = str((Path.cwd() / pattern).resolve())

        matches = sorted(Path(match_path) for match_path in glob(glob_pattern, recursive=True))

        file_matches = [path for path in matches if path.is_file()]
        if not file_matches:
            raise RuntimeError(f"No files matched pattern '{pattern}' (from '{file_url}')")

        fragments: List[str] = []
        for path in file_matches:
            fragments.append(path.read_text(encoding="utf-8"))

        return fragments

    def _catalog_to_markdown(self, catalog: Catalog) -> str:
        """Convert catalog structure into a readable markdown document."""

        lines: List[str] = ["# Catalog"]

        if not catalog.organizations:
            lines.append("")
            lines.append("_No organizations defined._")
            lines.append("")
            return "\n".join(lines)

        for organization in catalog.organizations:
            name = organization.name or "Unnamed organization"

            lines.append("")
            lines.append(f"## {name}")
            lines.append("")

            if not organization.collections:
                lines.append("_No collections defined._")
                continue

            for collection in organization.collections:
                url = collection.url.strip()
                if url:
                    lines.append(f"- {url}")
                else:
                    lines.append("- (missing url)")

        lines.append("")
        return "\n".join(lines)
