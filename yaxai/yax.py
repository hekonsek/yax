from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, quote, unquote, urlparse
from urllib.request import Request, urlopen

import yaml

from yaxai.ghurl import GitHubFile


DEFAULT_AGENTSMD_OUTPUT = "AGENTS.md"
DEFAULT_AGENTSMD_CONFIG_FILENAME = "yax.yml"


@dataclass
class AgentsmdBuildConfig:
    urls: Optional[List[str]] = None
    output: str = DEFAULT_AGENTSMD_OUTPUT
    name: Optional[str] = None

    @staticmethod
    def resolve_config_path(
        config_path: Path
    ) -> Path:
        """Resolve the expected config path, allowing parent fallback for defaults."""

        config_path = Path(config_path)
        if not config_path.is_absolute():
            config_path = config_path.resolve(strict=False)

        if config_path.exists():
            return config_path

        cwd = Path.cwd()
        is_default_selection = (
            config_path.name == DEFAULT_AGENTSMD_CONFIG_FILENAME
            and config_path.parent == cwd
        )

        if is_default_selection and cwd.parent != cwd and cwd.name:
            fallback_path = cwd.parent / f"{cwd.name}-{DEFAULT_AGENTSMD_CONFIG_FILENAME}"
            if fallback_path.exists():
                return fallback_path

        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    @classmethod
    def parse_yml(cls, config_file_path: str | Path) -> AgentsmdBuildConfig:
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

        if urls is None or len(urls) == 0:
            raise ValueError("Agentsmd build config must specify at least one source URL in 'build.agentsmd.from'")

        if not isinstance(urls, list):
            raise ValueError("Expected 'from' to be a list of strings in config file")

        normalized_urls: List[str] = []
        for url in urls:
            if not isinstance(url, str):
                raise ValueError("Expected every entry in 'from' to be a string")
            stripped_url = url.strip()
            if stripped_url:
                normalized_urls.append(stripped_url)
            else:
                raise ValueError("Source URLs in 'build.agentsmd.from' must be non-empty strings")

        name_value: Optional[str] = None
        metadata_raw = agentsmd_section.get("metadata")
        if metadata_raw is not None:
            if not isinstance(metadata_raw, dict):
                raise ValueError("Expected 'metadata' to be a mapping in config file")

            raw_name = metadata_raw.get("name")
            if raw_name is not None:
                if not isinstance(raw_name, str):
                    raise ValueError("Expected 'metadata.name' to be a string")
                stripped_name = raw_name.strip()
                if not stripped_name:
                    raise ValueError("'metadata.name' must be a non-empty string when provided")
                name_value = stripped_name

        return cls(urls=normalized_urls, output=output, name=name_value)


DEFAULT_CATALOG_OUTPUT = "yax-catalog.json"


@dataclass
class CatalogSource:
    url: str

    def __post_init__(self) -> None:
        self.url = self.url.strip()
        if not self.url:
            raise ValueError("Catalog source url must be a non-empty string")


@dataclass
class CatalogBuildConfig:
    organization: str
    sources: List[CatalogSource] = field(default_factory=list)
    output: str = DEFAULT_CATALOG_OUTPUT

    def __post_init__(self) -> None:
        normalized_sources: List[CatalogSource] = []
        for entry in self.sources:
            if isinstance(entry, CatalogSource):
                source = entry
            elif isinstance(entry, str):
                source = CatalogSource(url=entry)
            else:
                raise TypeError("Catalog sources must be strings or CatalogSource instances")
            normalized_sources.append(source)

        self.sources = normalized_sources

    @classmethod
    def open_catalog_build_config(cls, config_file_path: str | Path) -> "CatalogBuildConfig":
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
            raise ValueError("Expected 'from' to be a list in config file")

        sources: List[CatalogSource] = []
        for entry in raw_sources:
            if isinstance(entry, str):
                stripped = entry.strip()
                if stripped:
                    sources.append(CatalogSource(url=stripped))
                continue

            if isinstance(entry, dict):
                url_value = entry.get("url")
                if not isinstance(url_value, str) or not url_value.strip():
                    raise ValueError("Catalog source objects must include a non-empty 'url' field")

                if "name" in entry:
                    raise ValueError(
                        "Catalog source 'name' is no longer supported; define metadata in the referenced config"
                    )

                if "metadata" in entry:
                    raise ValueError(
                        "Catalog source 'metadata' is no longer supported; define metadata in the referenced config"
                    )

                sources.append(CatalogSource(url=url_value.strip()))
                continue

            raise ValueError("Catalog sources must be strings or objects with a 'url'")

        output = catalog_section.get("output", DEFAULT_CATALOG_OUTPUT)
        if output is None:
            output = DEFAULT_CATALOG_OUTPUT
        if not isinstance(output, str):
            raise ValueError("Expected 'output' to be a string in config file")

        return cls(organization=organization, sources=sources, output=output)


@dataclass
class CatalogCollection:
    url: str
    name: Optional[str] = None

    def __post_init__(self) -> None:
        self.url = self.url.strip()
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("Catalog collection name must be a non-empty string when provided")

    @classmethod
    def from_mapping(cls, data: Any) -> "CatalogCollection":
        if not isinstance(data, dict):
            raise ValueError("Expected collection entry to be an object")

        url_value = data.get("url", "")
        if not isinstance(url_value, str):
            raise ValueError("Expected collection 'url' to be a string")

        name_value: Optional[str] = None

        if "name" in data:
            direct_name = data.get("name")
            if direct_name is not None:
                if not isinstance(direct_name, str):
                    raise ValueError("Expected collection 'name' to be a string")
                stripped_direct_name = direct_name.strip()
                if not stripped_direct_name:
                    raise ValueError("Collection 'name' must be a non-empty string when provided")
                name_value = stripped_direct_name

        if name_value is None and "metadata" in data:
            metadata_raw = data.get("metadata")
            if metadata_raw is not None:
                if not isinstance(metadata_raw, dict):
                    raise ValueError("Expected collection 'metadata' to be a mapping")
                meta_name = metadata_raw.get("name")
                if meta_name is not None:
                    if not isinstance(meta_name, str):
                        raise ValueError("Expected collection 'metadata.name' to be a string")
                    stripped_meta_name = meta_name.strip()
                    if not stripped_meta_name:
                        raise ValueError(
                            "Collection 'metadata.name' must be a non-empty string when provided"
                        )
                    name_value = stripped_meta_name

        return cls(url=url_value.strip(), name=name_value)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"url": self.url}
        if self.name:
            data["name"] = self.name
        return data


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "collections": [collection.to_dict() for collection in self.collections],
        }


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "organizations": [org.to_dict() for org in self.organizations],
        }


class Yax:
    """Core Yax entry point placeholder."""

    USER_AGENT = "yax/1.0"

    def __init__(self) -> None:
        self._github_token: Optional[str] = None

    def build_agentsmd(self, config: AgentsmdBuildConfig) -> None:
        """Download agent markdown fragments and concatenate them into the output file."""

        urls = config.urls or []

        fragments: List[str] = []
        for url in urls:
            if url.startswith("file:"):
                fragments.extend(self._read_local_sources(url))
                continue

            ghfile = GitHubFile.parse(url)
            fragments.append(ghfile.download())

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
                    collections=[
                        CatalogCollection(
                            url=source.url,
                            name=self._discover_catalog_collection_name(source.url),
                        )
                        for source in config.sources
                    ],
                )
            ]
        )

        output_path = Path(config.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            json.dumps(catalog.to_dict(), indent=2, sort_keys=True),
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

    def _discover_catalog_collection_name(self, source_url: str) -> Optional[str]:
        """Load the referenced Yax config and extract the collection display name."""

        config_text = self._read_catalog_source_text(source_url)
        config_data = self._parse_catalog_source_yaml(config_text, source_url)

        build_section = config_data.get("build")
        if not isinstance(build_section, dict):
            return None

        agentsmd_section = build_section.get("agentsmd")
        if not isinstance(agentsmd_section, dict):
            return None

        metadata = agentsmd_section.get("metadata")
        if not isinstance(metadata, dict):
            return None

        raw_name = metadata.get("name")
        if raw_name is None:
            return None
        if not isinstance(raw_name, str):
            raise ValueError(
                f"Catalog source '{source_url}' metadata 'name' must be a string"
            )

        stripped = raw_name.strip()
        if not stripped:
            raise ValueError(
                f"Catalog source '{source_url}' metadata 'name' must be a non-empty string"
            )

        return stripped

    def _parse_catalog_source_yaml(self, contents: str, source_url: str) -> Dict[str, Any]:
        """Parse YAML contents from a catalog source and validate the structure."""

        try:
            data = yaml.safe_load(contents) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - yaml parser detail path
            raise RuntimeError(
                f"Failed to parse YAML from catalog source '{source_url}': {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"Catalog source '{source_url}' must contain a YAML mapping at the root"
            )

        return data

    def _read_catalog_source_text(self, source_url: str) -> str:
        """Retrieve the raw YAML contents for the provided catalog source URL."""

        parsed = urlparse(source_url)
        scheme = parsed.scheme.lower()

        if scheme == "file":
            path = self._file_uri_to_path(parsed)
            try:
                return path.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(
                    f"Failed to read catalog source '{source_url}': {exc}"
                ) from exc
        else:
            ghfile = GitHubFile.parse(source_url)
            return ghfile.download()


    @staticmethod
    def _file_uri_to_path(parsed: ParseResult) -> Path:
        """Convert a file:// URI parse result into a filesystem path."""

        path = unquote(parsed.path or "")
        if parsed.netloc:
            if path.startswith("/"):
                return Path(f"/{parsed.netloc}{path}")
            return Path(f"/{parsed.netloc}/{path}")

        return Path(path)

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
                display_name = collection.name

                if display_name and url:
                    lines.append(f"- [{display_name}]({url})")
                elif url:
                    lines.append(f"- {url}")
                elif display_name:
                    lines.append(f"- {display_name}")
                else:
                    lines.append("- (missing url)")

        lines.append("")
        return "\n".join(lines)
