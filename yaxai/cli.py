"""Command line interface for the Yax project."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

import typer

from .yax import AgentsmdBuildConfig, Yax


def _green(text: str) -> str:
    return typer.style(str(text), fg=typer.colors.GREEN)


DEFAULT_CONFIG_FILENAME = "yax.yml"

app = typer.Typer(help="Interact with Yax features from the command line.", no_args_is_help=True)

agentsmd_app = typer.Typer(help="Work with agentsmd build resources.", no_args_is_help=True)
app.add_typer(agentsmd_app, name="agentsmd")

def _load_agentsmd_config(config_path: Path) -> AgentsmdBuildConfig:
    """Load and return the agentsmd build configuration from the provided path."""

    if not config_path.exists():
        typer.echo(f"Configuration file not found: {config_path}")
        raise typer.Exit(code=1)

    return AgentsmdBuildConfig.open_agentsmd_build_config(str(config_path))

def _build_agentsmd(config: Path, output: Optional[Path]) -> None:
    """Execute the agentsmd build workflow."""

    build_config = _load_agentsmd_config(config)

    if output is not None:
        build_config = replace(build_config, output=str(output))

    yax = Yax()

    try:
        yax.build_agentsmd(build_config)
    except Exception as exc:  # pragma: no cover - relies on network errors
        typer.echo(f"Error building agentsmd: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Generated agents markdown at {_green(build_config.output)}.")


@agentsmd_app.command("build")
def agentsmd_build(
    config: Path = typer.Option(
        Path(DEFAULT_CONFIG_FILENAME),
        "--config",
        "-c",
        resolve_path=True,
        help="Path to the YAML configuration file.",
        show_default=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Override the output file path for the generated AGENTS.md.",
    ),
):
    """Load the agentsmd build configuration and report its status."""

    _build_agentsmd(config, output)


@app.command("build")
def build_alias(
    config: Path = typer.Option(
        Path(DEFAULT_CONFIG_FILENAME),
        "--config",
        "-c",
        resolve_path=True,
        help="Path to the YAML configuration file.",
        show_default=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Override the output file path for the generated AGENTS.md.",
    ),
):
    """Shorter alias for `yax agentsmd build`."""

    _build_agentsmd(config, output)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    app()
