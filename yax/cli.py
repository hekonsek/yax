"""Command line interface for the Yax project."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

import typer

from .yax import AgentsmdBuildConfig, Yax


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

@agentsmd_app.command()
def build(
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

    build_config = _load_agentsmd_config(config)

    if output is not None:
        build_config = replace(build_config, output=str(output))

    urls = build_config.urls or []
    typer.echo(
        f"Loaded agentsmd build config from {config.resolve()} ({len(urls)} URL(s))."
    )

    yax = Yax()

    try:
        generated_path = yax.build_agentsmd(build_config)
    except Exception as exc:  # pragma: no cover - relies on network errors
        typer.echo(f"Error building agentsmd: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Generated agents markdown at {generated_path.resolve()}.")


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    app()
