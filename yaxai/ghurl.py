from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


_ALLOWED_SCHEMES = {"http", "https"}
_VALID_HOSTS = {"github.com", "raw.githubusercontent.com"}


@dataclass(frozen=True)
class GitHubUrl:
    url: str

    @classmethod
    def parse(cls, value: str) -> GitHubUrl:
        if not isinstance(value, str):
            raise TypeError("GitHubUrl.parse expects a string argument")

        candidate = value.strip()
        if not candidate:
            raise ValueError("GitHub URL cannot be empty")

        parsed = urlparse(candidate)
        scheme = parsed.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            raise ValueError("GitHub URL must start with http:// or https://")

        if not parsed.netloc:
            raise ValueError("GitHub URL must include a hostname")

        host = parsed.netloc.lower()
        normalized_host = host[4:] if host.startswith("www.") else host
        if normalized_host not in _VALID_HOSTS:
            raise ValueError("GitHub URL must point to github.com or raw.githubusercontent.com")

        segments = [segment for segment in parsed.path.split("/") if segment]
        if normalized_host == "github.com":
            if len(segments) < 2:
                raise ValueError("GitHub URL must include repository owner and name")
        else:  # raw.githubusercontent.com
            if len(segments) < 4:
                raise ValueError("GitHub raw URL must include owner, repository, ref, and file path")

        return cls(candidate)
