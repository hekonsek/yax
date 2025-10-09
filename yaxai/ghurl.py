from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen


_ALLOWED_SCHEMES = {"http", "https"}
_VALID_HOSTS = {"github.com", "raw.githubusercontent.com"}


@dataclass(frozen=True)
class GitHubFile:
    url: str

    @classmethod
    def parse(cls, value: str) -> GitHubFile:
        if not isinstance(value, str):
            raise TypeError("GitHubFile.parse expects a string argument")

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
            ui_segments = segments
        else:  # raw.githubusercontent.com
            if len(segments) < 4:
                raise ValueError("GitHub raw URL must include owner, repository, ref, and file path")
            owner, repository, ref, *file_segments = segments
            ui_segments = [owner, repository, "blob", ref, *file_segments]

        ui_path = "/" + "/".join(ui_segments)
        normalized_url = urlunparse(
            (
                "https",
                "github.com",
                ui_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

        return cls(normalized_url)

    def raw(self) -> str:
        parsed = urlparse(self.url)

        segments = [segment for segment in parsed.path.split("/") if segment]

        owner, repository, _, ref, *file_segments = segments
        raw_path = "/" + "/".join([owner, repository, ref, *file_segments])

        return urlunparse(
            (
                "https",
                "raw.githubusercontent.com",
                raw_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def is_visible(self, timeout: float = 10.0) -> bool:
        raw_url = self.raw()
        request = Request(raw_url, method="HEAD")

        try:
            with urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", response.getcode())
        except HTTPError as error:
            status = error.code
        except URLError:
            return False

        return status not in {401, 403, 404}

    def download(self) -> str:
        if not self.is_visible():
            raise RuntimeError(f"GitHub file '{self.url}' is not visible.")

        raw_url = self.raw()
        request = Request(raw_url)

        try:
            with urlopen(request) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Failed to download '{self.url}': {error}") from error
