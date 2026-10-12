"""AcreEdge Command Line Interface."""

from __future__ import annotations

import json
import click
from rich.console import Console

from acreedge import __author__, __version__
from acreedge.config import AcreEdgeSettings
from acreedge.db.sql_validator import SQLRawExportValidator

console = Console()


@click.group()
def cli() -> None:
    """AcreEdge: Autonomous Underwriting Engine & Municipal Deed Ingestion CLI."""
    pass


@cli.command("version")
def version_cmd() -> None:
    """Display AcreEdge package version and author."""
    console.print(f"[bold cyan]AcreEdge[/bold cyan] v{__version__} by {__author__}")


@cli.command("info")
def info_cmd() -> None:
    """Display system status and configuration summary."""
    settings = AcreEdgeSettings()
    console.print("[bold green]=== AcreEdge System Summary ===[/bold green]")
    console.print(f"Environment: [yellow]{settings.environment}[/yellow]")
    console.print(f"PostgreSQL DB: [cyan]{settings.db.name}[/cyan] ({settings.db.host}:{settings.db.port})")
    console.print(f"MCP Server Port: [cyan]{settings.mcp.port}[/cyan]")
    console.print(f"Vector Dimension: [magenta]{settings.rag.vector_dim}[/magenta]")
    console.print(f"Underwriting Swarm Agents: [blue]{len(settings.swarm.roles)}[/blue] configured")


@cli.command("validate-config")
def validate_config_cmd() -> None:
    """Validate environment settings and print active config JSON."""
    settings = AcreEdgeSettings()
    console.print(json.dumps(settings.model_dump(), indent=2))


@cli.command("generate-sql")
def generate_sql_cmd() -> None:
    """Output PostgreSQL SQL script to clean and stage raw deed exports."""
    validator = SQLRawExportValidator()
    ddl = validator.generate_schema_ddl()
    sql = validator.generate_validation_sql()
    console.print("[bold yellow]-- AcreEdge PostgreSQL Cleanup & Validation Script --[/bold yellow]")
    console.print(ddl)
    console.print(sql)


if __name__ == "__main__":
    cli()
