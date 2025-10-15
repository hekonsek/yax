from __future__ import annotations

import json
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import ParseResult, quote, unquote, urlparse

import yaml

from yaxai.ghurl import GitHubFile

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_AGENTSMD_OUTPUT = "AGENTS.md"
DEFAULT_AGENTSMD_CONFIG_FILENAME = "yax.yml"

class AgentsmdBuildConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    urls: List[str] = Field(default_factory=list, alias="from")
    output: str = DEFAULT_AGENTSMD_OUTPUT
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("urls")
    @classmethod
    def _urls_must_not_be_empty(cls, urls: List[str]) -> List[str]:
        if not urls:
            raise ValueError("urls list must not be empty")
        for url in urls:
            if not isinstance(url, str) or not url.strip():
                raise ValueError("each URL must be a non-empty string")
        return urls

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

        return AgentsmdBuildConfig.model_validate(
            data.get("build", {}).get("agentsmd", {})
        )


    def save(self, config_path: Path) -> None:
        """Persist the configuration to disk, preserving unrelated sections."""

        config_path = Path(config_path)

        if config_path.exists():
            try:
                raw_text = config_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(f"Failed to read configuration '{config_path}': {exc}") from exc

            try:
                data = yaml.safe_load(raw_text) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in '{config_path}': {exc}") from exc

            if not isinstance(data, dict):
                raise ValueError(f"Configuration '{config_path}' must contain a mapping at the root")
        else:
            data = {"build": {"agentsmd": self.model_dump(by_alias=True)}}

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(data, sort_keys=False),
            encoding="utf-8",
        )


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
    output: Optional[str] = None

    def __post_init__(self) -> None:
        self.url = self.url.strip()
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("Catalog collection name must be a non-empty string when provided")
        if self.output is not None:
            self.output = self.output.strip()
            if not self.output:
                raise ValueError("Catalog collection output must be a non-empty string when provided")

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

        output_value: Optional[str] = None
        if "output" in data:
            direct_output = data.get("output")
            if direct_output is not None:
                if not isinstance(direct_output, str):
                    raise ValueError("Expected collection 'output' to be a string")
                stripped_output = direct_output.strip()
                if not stripped_output:
                    raise ValueError("Collection 'output' must be a non-empty string when provided")
                output_value = stripped_output

        return cls(url=url_value.strip(), name=name_value, output=output_value)

    def output_url(self) -> str:
        """Return URL pointing to the collection output artifact."""

        output_filename = Path(self.output or "_agents.md").name
        if not output_filename:
            raise ValueError("Catalog collection 'output' must include a file name")

        parsed = urlparse(self.url)
        path = parsed.path or ""

        if not path or path.endswith("/"):
            raise ValueError("Catalog collection 'url' must reference a file path")

        path_segments = path.split("/")
        path_segments[-1] = quote(output_filename)
        new_path = "/".join(path_segments)

        return parsed._replace(path=new_path).geturl()

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"url": self.url}
        if self.name:
            data["name"] = self.name
        if self.output is not None:
            data["output"] = self.output
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


class Discovery:
    """Load catalog information and expose its collections."""

    DEFAULT_CATALOG_PATH = Path.home() / ".yax" / DEFAULT_CATALOG_OUTPUT

    def __init__(self, catalog_path: Optional[Path | str] = None) -> None:
        if catalog_path is None:
            self._catalog_path = self.DEFAULT_CATALOG_PATH
        else:
            self._catalog_path = Path(catalog_path)

    def discover(self) -> List[CatalogCollection]:
        catalog_path = self._catalog_path
        if not catalog_path.exists():
            raise FileNotFoundError(f"Catalog file not found: {catalog_path}")

        try:
            catalog_data = json.loads(catalog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid catalog JSON in '{catalog_path}': {exc}") from exc

        catalog = Catalog.from_mapping(catalog_data)

        collections: List[CatalogCollection] = []
        for organization in catalog.organizations:
            collections.extend(organization.collections)

        return collections


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

        collections: List[CatalogCollection] = []
        for source in config.sources:
            collection_name, collection_output = self._discover_catalog_collection_details(source.url)
            collections.append(
                CatalogCollection(
                    url=source.url,
                    name=collection_name,
                    output=collection_output,
                )
            )

        catalog = Catalog(
            organizations=[
                CatalogOrganization(
                    name=config.organization,
                    collections=collections,
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

    def _discover_catalog_collection_details(self, source_url: str) -> Tuple[Optional[str], Optional[str]]:
        """Load the referenced Yax config and extract collection metadata."""

        config_text = self._read_catalog_source_text(source_url)
        config_data = self._parse_catalog_source_yaml(config_text, source_url)

        build_section = config_data.get("build")
        if not isinstance(build_section, dict):
            return (None, None)

        agentsmd_section = build_section.get("agentsmd")
        if not isinstance(agentsmd_section, dict):
            return (None, None)

        name_value: Optional[str] = None
        metadata = agentsmd_section.get("metadata")
        if isinstance(metadata, dict):
            raw_name = metadata.get("name")
            if raw_name is not None:
                if not isinstance(raw_name, str):
                    raise ValueError(
                        f"Catalog source '{source_url}' metadata 'name' must be a string"
                    )

                stripped_name = raw_name.strip()
                if not stripped_name:
                    raise ValueError(
                        f"Catalog source '{source_url}' metadata 'name' must be a non-empty string"
                    )
                name_value = stripped_name

        output_value: Optional[str] = None
        raw_output = agentsmd_section.get("output", DEFAULT_AGENTSMD_OUTPUT)
        if raw_output is None:
            raw_output = DEFAULT_AGENTSMD_OUTPUT

        if raw_output is not None:
            if not isinstance(raw_output, str):
                raise ValueError(
                    f"Catalog source '{source_url}' 'output' must be a string"
                )
            stripped_output = raw_output.strip()
            if not stripped_output:
                raise ValueError(
                    f"Catalog source '{source_url}' 'output' must be a non-empty string when provided"
                )
            output_value = stripped_output

        return (name_value, output_value)

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
