from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import yaml


@dataclass
class AgentsmdBuildConfig:
    urls: Optional[List[str]] = None

    @classmethod
    def open_agentsmd_build_config(cls, config_file_path: str) -> "AgentsmdBuildConfig":
        """Load Agentsmd build configuration from YAML file."""
        with open(config_file_path, "r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}

        urls = (
            data.get("build", {})
            .get("agentsmd", {})
            .get("from", {})
            .get("urls")
        )

        if urls is None:
            return cls()

        if not isinstance(urls, list):
            raise ValueError("Expected 'urls' to be a list of strings in config file")

        normalized_urls: List[str] = []
        for url in urls:
            if not isinstance(url, str):
                raise ValueError("Expected every entry in 'urls' to be a string")
            normalized_urls.append(url)

        return cls(urls=normalized_urls)


class Yax:
    """Core Yax entry point placeholder."""
    pass
