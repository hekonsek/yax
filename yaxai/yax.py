from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from glob import glob
from pathlib import Path
from typing import Any, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, quote, unquote, urlparse
from urllib.request import Request, urlopen

import yaml


DEFAULT_AGENTSMD_OUTPUT = "AGENTS.md"
DEFAULT_AGENTSMD_CONFIG_FILENAME = "yax.yml"


@dataclass
class AgentsmdBuildConfig:
    urls: Optional[List[str]] = None
    output: str = DEFAULT_AGENTSMD_OUTPUT

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

        return cls(urls=normalized_urls, output=output)


DEFAULT_CATALOG_OUTPUT = "yax-catalog.json"


@dataclass
class CatalogBuildConfig:
    organization: str
    sources: List[str] = field(default_factory=list)
    output: str = DEFAULT_CATALOG_OUTPUT

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

            fragments.append(self._download_remote_source(url))

        output_path = Path(config.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        combined_content = "\n\n".join(fragments)
        output_path.write_text(combined_content, encoding="utf-8")

    def _download_remote_source(self, url: str) -> str:
        """Retrieve remote source content with GitHub authentication support."""

        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise RuntimeError(f"Unsupported URL scheme for '{url}'")

        host = parsed.netloc.lower()

        if host == "raw.githubusercontent.com":
            return self._download_github_raw_with_fallback(parsed, url)

        if host in {"github.com", "www.github.com"}:
            return self._download_github_ui_url(parsed, url)

        try:
            return self._download_plain(url)
        except URLError as exc:  # pragma: no cover - network/IO error path
            raise RuntimeError(f"Failed to download '{url}': {exc}") from exc

    def _download_plain(self, url: str, extra_headers: Optional[dict[str, str]] = None) -> str:
        """Download text content from a URL using optional extra headers."""

        if extra_headers:
            headers = self._build_request_headers(extra_headers)
            request = Request(url, headers=headers)
            opener_target = request
        else:
            opener_target = url

        with urlopen(opener_target) as response:
            return response.read().decode("utf-8")

    def _build_request_headers(self, extra_headers: dict[str, str]) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": self.USER_AGENT}
        headers.update(extra_headers)
        return headers

    def _download_github_raw_with_fallback(self, parsed: ParseResult, original_url: str) -> str:
        """Attempt raw download, falling back to the API for private content."""

        try:
            return self._download_plain(original_url)
        except HTTPError as exc:
            if exc.code in {401, 403, 404}:
                return self._download_github_from_segments(parsed, original_url)
            raise RuntimeError(f"Failed to download '{original_url}': {exc}") from exc
        except URLError as exc:  # pragma: no cover - network/IO error path
            raise RuntimeError(f"Failed to download '{original_url}': {exc}") from exc

    def _download_github_ui_url(self, parsed: ParseResult, original_url: str) -> str:
        """Download a GitHub UI URL via the REST API using authentication."""

        segments = [segment for segment in parsed.path.lstrip("/").split("/") if segment]
        if len(segments) < 5:
            raise RuntimeError(
                "GitHub URL must include owner, repo, ref, and file path (expected '/<owner>/<repo>/blob/<ref>/<file>')."
            )

        owner, repo = segments[0], segments[1]
        marker = segments[2]

        if marker not in {"blob", "raw"}:
            raise RuntimeError(
                "GitHub URL must reference a file via the 'blob' or 'raw' view (e.g. https://github.com/<org>/<repo>/blob/<ref>/<path>')."
            )

        remainder = segments[3:]
        return self._download_github_repo_content(owner, repo, remainder, original_url)

    def _download_github_from_segments(self, parsed: ParseResult, original_url: str) -> str:
        """Fallback helper to download a file given a raw.githubusercontent.com URL."""

        segments = [segment for segment in parsed.path.lstrip("/").split("/") if segment]
        if len(segments) < 4:
            raise RuntimeError(
                f"GitHub raw URL '{original_url}' must include owner, repo, ref, and file path."
            )

        owner, repo = segments[0], segments[1]
        remainder = segments[2:]
        return self._download_github_repo_content(owner, repo, remainder, original_url)

    def _download_github_repo_content(
        self, owner: str, repo: str, remainder: List[str], original_url: str
    ) -> str:
        """Iterate potential ref/path splits and download content via the GitHub API."""

        if len(remainder) < 2:
            raise RuntimeError(
                f"GitHub URL '{original_url}' must include both a ref and file path."
            )

        last_not_found: Optional[HTTPError] = None
        for split in range(1, len(remainder)):
            ref = "/".join(remainder[:split])
            file_path = "/".join(remainder[split:])

            try:
                return self._download_github_repo_api(owner, repo, ref, file_path, original_url)
            except HTTPError as exc:  # pragma: no cover - GitHub API failures
                if exc.code == 404:
                    last_not_found = exc
                    continue
                raise RuntimeError(f"Failed to download '{original_url}' via GitHub API: {exc}") from exc

        if last_not_found is not None:
            raise RuntimeError(f"GitHub API reported 404 for '{original_url}'") from last_not_found

        raise RuntimeError(f"GitHub URL '{original_url}' does not contain a downloadable file path")

    def _download_github_repo_api(
        self, owner: str, repo: str, ref: str, file_path: str, original_url: str
    ) -> str:
        """Perform the authenticated GitHub API request for repository file content."""

        token = self._get_github_token()

        encoded_path = "/".join(quote(part, safe="") for part in file_path.split("/"))
        encoded_ref = quote(ref, safe="")
        api_url = (
            f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}?ref={encoded_ref}"
        )

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3.raw",
        }

        try:
            return self._download_plain(api_url, headers)
        except HTTPError:
            raise
        except URLError as exc:  # pragma: no cover - network/IO error path
            raise RuntimeError(f"Failed to download '{original_url}' via GitHub API: {exc}") from exc

    def _get_github_token(self) -> str:
        """Return a GitHub token retrieved via the GitHub CLI."""

        if self._github_token is not None:
            return self._github_token

        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "GitHub CLI ('gh') is required to download private GitHub content."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Unable to obtain GitHub token via 'gh auth token'. Ensure you are logged in."
            ) from exc

        token = result.stdout.strip()
        if not token:
            raise RuntimeError("Received empty token from 'gh auth token'.")

        self._github_token = token
        return token

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
