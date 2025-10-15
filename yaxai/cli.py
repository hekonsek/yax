"""Command line interface for the Yax project."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

import typer

from .yax import (
    DEFAULT_AGENTSMD_CONFIG_FILENAME,
    DEFAULT_CATALOG_OUTPUT,
    AgentsmdBuildConfig,
    CatalogBuildConfig,
    Discovery,
    Yax,
)


def _green(text: str | Path) -> str:
    return typer.style(str(text), fg=typer.colors.GREEN)


DEFAULT_CONFIG_FILENAME = DEFAULT_AGENTSMD_CONFIG_FILENAME
DEFAULT_CATALOG_CONFIG_FILENAME = "yax-catalog.yml"
DEFAULT_CATALOG_SOURCE_FILENAME = DEFAULT_CATALOG_OUTPUT

app = typer.Typer(help="Interact with Yax features from the command line.", no_args_is_help=True)

agentsmd_app = typer.Typer(help="Work with agentsmd build resources.", no_args_is_help=True)
app.add_typer(agentsmd_app, name="agentsmd")
catalog_app = typer.Typer(help="Build catalog artifacts.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")


def _format_collection_label(collection: CatalogCollection) -> str:
    """Return the display label for a collection."""

    if collection.name and collection.name.strip():
        return collection.name.strip()

    try:
        url = collection.output_url().strip()
        if url:
            return url
    except Exception:  # pragma: no cover - defensive fallback
        pass

    return collection.url.strip()


def _collection_target_url(collection: CatalogCollection) -> str:
    """Return URL that should be added to the agentsmd sources list."""

    try:
        url = collection.output_url().strip()
    except Exception:  # pragma: no cover - defensive fallback
        url = collection.url.strip()

    if not url:
        raise ValueError("Collection URL is empty and cannot be added to the configuration")

    return url

def _load_agentsmd_config(config_path: Path) -> AgentsmdBuildConfig:
    """Load and return the agentsmd build configuration from the provided path."""

    try:
        resolved_config_path = AgentsmdBuildConfig.resolve_config_path(config_path)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if resolved_config_path != config_path:
        typer.echo(f"Using fallback configuration file: {_green(resolved_config_path)}")

    return AgentsmdBuildConfig.parse_yml(str(resolved_config_path))

def _build_agentsmd(config: Path, output: Optional[Path]) -> None:
    """Execute the agentsmd build workflow."""

    build_config = _load_agentsmd_config(config)

    if output is not None:
        build_config = build_config.model_copy(update={"output": str(output)})

    yax = Yax()

    try:
        yax.build_agentsmd(build_config)
    except Exception as exc:  # pragma: no cover - relies on network errors
        typer.echo(f"Error building agentsmd: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Generated agents markdown: {_green(build_config.output)}")


def _load_catalog_config(config_path: Path) -> CatalogBuildConfig:
    """Load and return the catalog build configuration from the provided path."""

    if not config_path.exists():
        typer.echo(f"Configuration file not found: {config_path}")
        raise typer.Exit(code=1)

    return CatalogBuildConfig.open_catalog_build_config(str(config_path))


def _build_catalog(config: Path, output: Optional[Path]) -> None:
    """Execute the catalog build workflow."""

    build_config = _load_catalog_config(config)

    if output is not None:
        build_config = replace(build_config, output=str(output))

    yax = Yax()

    try:
        yax.build_catalog(build_config)
    except Exception as exc:  # pragma: no cover - relies on filesystem and IO errors
        typer.echo(f"Error building catalog: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Generated catalog at {_green(build_config.output)}.")


def _export_catalog(source: Path, format_name: str) -> None:
    """Export catalog JSON into the requested format."""

    if not source.exists():
        typer.echo(f"Catalog source file not found: {source}")
        raise typer.Exit(code=1)

    yax = Yax()

    try:
        output_path = yax.export_catalog(source, format_name)
    except Exception as exc:  # pragma: no cover - relies on filesystem and parsing errors
        typer.echo(f"Error exporting catalog: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Exported catalog to {_green(output_path)}.")


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


@agentsmd_app.command("discover")
def agentsmd_discover(
    catalog: Optional[Path] = typer.Option(
        None,
        "--catalog",
        "-c",
        resolve_path=True,
        help="Path to the catalog JSON file. Defaults to ~/.yax/yax-catalog.json.",
    ),
) -> None:
    """List collections discovered from the catalog JSON."""

    discovery = Discovery(catalog)

    try:
        collections = discovery.discover()
    except Exception as exc:
        typer.echo(f"Error discovering catalogs: {exc}")
        raise typer.Exit(code=1)

    if not collections:
        typer.echo("No catalog collections found.")
        return

    config_path = Path(DEFAULT_CONFIG_FILENAME)
    try:
        build_config = AgentsmdBuildConfig.parse_yml(config_path)
    except FileNotFoundError as exc:
        build_config = AgentsmdBuildConfig()

    while True:
        for index, collection in enumerate(collections, start=1):
            label = _format_collection_label(collection)
            typer.echo(f"{index}. {label}")

        selection = typer.prompt(
            "Select a collection number (press Enter to exit)",
            default="",
            show_default=False,
        ).strip()

        if not selection:
            return

        try:
            index = int(selection)
        except ValueError:
            typer.echo("Invalid selection. Enter a number from the list or press Enter to exit.")
            continue

        if not 1 <= index <= len(collections):
            typer.echo("Invalid selection. Enter a number from the list or press Enter to exit.")
            continue

        chosen = collections[index - 1]

        try:
            target_url = _collection_target_url(chosen)
        except ValueError as exc:
            typer.echo(f"Unable to add selection: {exc}")
            continue

        try:
            if target_url not in build_config.urls:
                build_config.urls.append(target_url)
                build_config.save(config_path)
                typer.echo(f"Added {target_url} to {config_path}.")
            else:
                typer.echo(f"{target_url} is already present in {config_path}.")
        except Exception as exc:
            typer.echo(f"Failed to update configuration: {exc}")
            raise typer.Exit(code=1)

@catalog_app.command("build")
def catalog_build(
    config: Path = typer.Option(
        Path(DEFAULT_CATALOG_CONFIG_FILENAME),
        "--config",
        "-c",
        resolve_path=True,
        help="Path to the YAML configuration file for catalog builds.",
        show_default=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Override the output file path for the generated catalog JSON.",
    ),
):
    """Build the catalog JSON artifact."""

    _build_catalog(config, output)


@catalog_app.command("export")
def catalog_export(
    source: Path = typer.Option(
        Path(DEFAULT_CATALOG_SOURCE_FILENAME),
        "--source",
        "-s",
        resolve_path=True,
        help="Path to the catalog JSON file to export.",
        show_default=True,
    ),
    format_name: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format for the exported catalog.",
        show_default=True,
    ),
):
    """Export the catalog JSON into alternative formats."""

    _export_catalog(source, format_name)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    app()
