"""Command line interface for the Yax project."""

from __future__ import annotations

from pathlib import Path

import typer

from .yax import AgentsmdBuildConfig


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
    config: Path = typer.Argument(
        Path(DEFAULT_CONFIG_FILENAME),
        resolve_path=True,
        help="Path to the YAML configuration file.",
        show_default=True,
    )
):
    """Load the agentsmd build configuration and report its status."""

    build_config = _load_agentsmd_config(config)

    urls = build_config.urls or []
    typer.echo(
        f"Loaded agentsmd build config from {config.resolve()} ({len(urls)} URL(s))."
    )


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    app()

