from __future__ import annotations

from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import List, Optional
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
