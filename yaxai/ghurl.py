from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import Request, urlopen


class GitHubTokenFinder:

    def find(self) -> Optional[str]:
        env_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if env_token:
            env_token = env_token.strip()
            if env_token:
                return env_token

        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            token = result.stdout.strip()
            if not token:
                return None
            return token
        except FileNotFoundError:
            return None
        except subprocess.CalledProcessError:
            return None
    

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
        if self.is_visible():
            return self._download_raw()

        return self._download_via_api()

    def _download_raw(self) -> str:
        request = Request(self.raw())

        try:
            with urlopen(request) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Failed to download '{self.url}': {error}") from error

    def _download_via_api(self) -> str:
        owner, repository, ref, file_segments = self._extract_components()
        encoded_path = "/".join(quote(segment, safe="") for segment in file_segments)
        encoded_ref = quote(ref, safe="")
        api_url = (
            f"https://api.github.com/repos/"
            f"{owner}/{repository}/contents/{encoded_path}?ref={encoded_ref}"
        )

        headers = {"Accept": "application/vnd.github.v3+json"}
        token = GitHubTokenFinder().find()
        if token:
            headers["Authorization"] = f"token {token}"

        request = Request(api_url, headers=headers)

        try:
            with urlopen(request) as response:
                payload = response.read().decode("utf-8")
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Failed to download '{self.url}' via GitHub API: {error}"
            ) from error

        try:
            descriptor = json.loads(payload)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Unexpected response format when downloading '{self.url}' via GitHub API"
            ) from error

        if descriptor.get("encoding") != "base64" or "content" not in descriptor:
            raise RuntimeError(
                f"Unexpected response when downloading '{self.url}' via GitHub API"
            )

        content = descriptor["content"].replace("\n", "")

        try:
            return base64.b64decode(content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise RuntimeError(
                f"Failed to decode content for '{self.url}' from GitHub API response"
            ) from error

    def _extract_components(self) -> tuple[str, str, str, list[str]]:
        parsed = urlparse(self.url)
        segments = [segment for segment in parsed.path.split("/") if segment]

        if len(segments) < 4:
            raise RuntimeError(f"GitHub URL '{self.url}' is not a file reference.")

        owner, repository, blob_keyword, ref, *file_segments = segments
        if blob_keyword != "blob":
            raise RuntimeError(f"GitHub URL '{self.url}' does not reference a blob.")

        if not file_segments:
            raise RuntimeError(f"GitHub URL '{self.url}' is missing the file path.")

        return owner, repository, ref, file_segments
