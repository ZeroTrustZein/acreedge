"""AcreEdge Command Line Interface."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import click
from rich.console import Console

from acreedge import __author__, __version__
from acreedge.agents.orchestrator import SwarmOrchestrator
from acreedge.config import AcreEdgeSettings, IngestionSettings
from acreedge.db.manager import DatabaseManager
from acreedge.db.sql_validator import SQLRawExportValidator
from acreedge.ingestion.pipeline import MunicipalDeedIngestionPipeline
from acreedge.mcp.server import AcreEdgeMCPServer
from acreedge.rag.engine import HybridRAGEngine
from acreedge.valuation.engine import ValuationEngine

console = Console()

_SAMPLE_DEEDS: List[Dict[str, Any]] = [
    {
        "parcel_id": "100-204-55A",
        "grantor": "Apex Holdings LLC",
        "grantee": "Meridian Realty Partners",
        "sale_date": "2026-03-15",
        "sale_price_raw": "$4,250,000.00",
        "deed_type": "SPECIAL WARRANTY",
        "book_page": "B204/P88",
    },
    {
        "parcel_id": "100-204-55B",
        "grantor": "John Doe Trust",
        "grantee": "John Doe Trust",
        "sale_date": "2026-04-01",
        "sale_price_raw": "$10.00",
        "deed_type": "QUITCLAIM",
        "book_page": "B204/P90",
    },
    {
        "parcel_id": "",
        "grantor": "Unknown Entity",
        "grantee": "Buyer Corp",
        "sale_date": "2026-04-10",
        "sale_price_raw": "$500,000.00",
        "deed_type": "DEED",
        "book_page": "B204/P92",
    },
    {
        "parcel_id": "100-204-56C",
        "grantor": "Beacon Hill Partners",
        "grantee": "Harborview Development LLC",
        "sale_date": "2026-05-20",
        "sale_price_raw": "1,850,000",
        "deed_type": "WARRANTY DEED",
        "book_page": "B205/P12",
    },
]


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
    db_info = f"{settings.db.host}:{settings.db.port}"
    console.print(f"PostgreSQL DB: [cyan]{settings.db.name}[/cyan] ({db_info})")
    console.print(f"MCP Server Port: [cyan]{settings.mcp.port}[/cyan]")
    console.print(f"Vector Dimension: [magenta]{settings.rag.vector_dim}[/magenta]")
    agent_count = len(settings.swarm.roles)
    console.print(f"Underwriting Swarm Agents: [blue]{agent_count}[/blue] configured")


@cli.command("validate-config")
def validate_config_cmd() -> None:
    """Validate environment settings and print active config JSON."""
    settings = AcreEdgeSettings()
    click.echo(json.dumps(settings.model_dump(), indent=2))


@cli.command("generate-sql")
@click.option(
    "--kind",
    type=click.Choice(["all", "ddl", "clean", "quarantine", "audit", "pipeline", "spatial"]),
    default="all",
    help="SQL artifact type to output.",
)
@click.option("--lat", type=float, default=40.7128, help="Latitude for spatial query.")
@click.option("--lon", type=float, default=-74.0060, help="Longitude for spatial query.")
@click.option("--radius", type=float, default=5.0, help="Radius in miles for spatial comps.")
def generate_sql_cmd(kind: str, lat: float, lon: float, radius: float) -> None:
    """Output PostgreSQL SQL scripts to clean, validate, and stage raw deed exports."""
    validator = SQLRawExportValidator()
    if kind == "ddl":
        click.echo(validator.generate_schema_ddl())
    elif kind == "clean":
        click.echo(validator.generate_validation_sql())
    elif kind == "quarantine":
        click.echo(validator.generate_quarantine_sql())
    elif kind == "audit":
        click.echo(validator.generate_audit_sql())
    elif kind == "pipeline":
        click.echo(validator.build_pipeline_sql())
    elif kind == "spatial":
        click.echo(
            validator.generate_spatial_comps_sql(
                latitude=lat, longitude=lon, radius_miles=radius
            )
        )
    else:
        ddl = validator.generate_schema_ddl()
        sql = validator.generate_validation_sql()
        console.print("[bold yellow]-- PostgreSQL Cleanup & Validation Script --[/bold yellow]")
        click.echo(ddl)
        click.echo(sql)


@cli.command("clean-export")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True),
    help="JSON file with raw deed records.",
)
@click.option("--min-price", type=float, default=None, help="Minimum sale price override.")
@click.option("--json-output", is_flag=True, help="Emit JSON instead of formatted text.")
def clean_export_cmd(
    file_path: Optional[str], min_price: Optional[float], json_output: bool
) -> None:
    """Clean and validate raw deed exports with PostgreSQL validation rules."""
    settings = IngestionSettings()
    if min_price is not None:
        settings.min_sale_price = min_price

    validator = SQLRawExportValidator(settings=settings)

    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        records = _SAMPLE_DEEDS

    res = validator.validate_batch(records)

    if json_output:
        click.echo(json.dumps(res, indent=2, default=str))
        return

    console.print("[bold green]=== Deed Export Validation Batch ===[/bold green]")
    console.print(f"Total Records: [bold]{res['total']}[/bold]")
    console.print(f"Valid Arm's-Length: [bold green]{res['valid_count']}[/bold green]")
    console.print(f"Invalid / Quarantined: [bold red]{res['invalid_count']}[/bold red]")

    for rec in res["valid_records"]:
        console.print(
            f"  - Parcel: [bold cyan]{rec['parcel_id']}[/bold cyan] | "
            f"Grantor: {rec['grantor']} -> Grantee: {rec['grantee']} | "
            f"Price: [green]${rec['sale_price']:,.2f}[/green] | Date: {rec['sale_date']} | "
            f"Type: {rec['deed_type']}"
        )


@cli.command("ingest")
@click.option(
    "--source",
    default="exports/raw_deeds_2026.csv",
    help="Source file path or identifier.",
)
@click.option("--run-cleaning", is_flag=True, help="Execute staged cleaning pipeline SQL.")
@click.option("--json-output", is_flag=True, help="Emit JSON output.")
def ingest_cmd(source: str, run_cleaning: bool, json_output: bool) -> None:
    """Ingest raw municipal deed export and run validation pipeline."""
    pipeline = MunicipalDeedIngestionPipeline()
    staging_res = pipeline.ingest_raw_export(source)

    cleaning_res: Optional[Dict[str, Any]] = None
    if run_cleaning:
        cleaning_res = pipeline.run_cleaning_pipeline()

    payload = {"staging": staging_res, "cleaning": cleaning_res}

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    console.print("[bold blue]=== Municipal Deed Ingestion Pipeline ===[/bold blue]")
    console.print(f"Source: [cyan]{source}[/cyan]")
    console.print(f"Staging Status: [green]{staging_res['status']}[/green]")
    if cleaning_res:
        console.print(f"Pipeline SQL Status: [bold green]{cleaning_res['status']}[/bold green]")


@cli.command("valuation")
@click.option("--noi", type=float, default=None, help="Net Operating Income ($).")
@click.option("--cap-rate", type=float, default=None, help="Cap rate (e.g. 0.065 for 6.5%).")
@click.option("--property-value", type=float, default=None, help="Property value ($).")
@click.option("--square-feet", type=float, default=None, help="Square footage.")
@click.option("--cash-flows", type=str, default=None, help="Comma-separated cash flows for DCF.")
@click.option(
    "--discount-rate", type=float, default=0.10, help="DCF discount rate (default: 0.10)."
)
@click.option("--terminal-value", type=float, default=0.0, help="DCF terminal value.")
@click.option("--json-output", is_flag=True, help="Emit JSON output.")
def valuation_cmd(
    noi: Optional[float],
    cap_rate: Optional[float],
    property_value: Optional[float],
    square_feet: Optional[float],
    cash_flows: Optional[str],
    discount_rate: float,
    terminal_value: float,
    json_output: bool,
) -> None:
    """Calculate valuation metrics (direct capitalization, comps, DCF)."""
    engine = ValuationEngine()
    results: Dict[str, Any] = {}

    if noi is not None and cap_rate is not None and cap_rate > 0:
        val = noi / cap_rate
        results["direct_cap_valuation"] = round(val, 2)
        if square_feet and square_feet > 0:
            results["value_per_sqft"] = round(val / square_feet, 2)

    if noi is not None and property_value is not None and property_value > 0:
        results["calculated_cap_rate"] = engine.calculate_cap_rate(noi, property_value)

    if cash_flows:
        cf_list = [float(x.strip()) for x in cash_flows.split(",") if x.strip()]
        results["dcf_valuation"] = engine.calculate_dcf(
            cash_flows=cf_list,
            discount_rate=discount_rate,
            terminal_value=terminal_value,
        )

    if not results and property_value is not None:
        results["property_value"] = property_value
        if square_feet and square_feet > 0:
            results["value_per_sqft"] = round(property_value / square_feet, 2)

    if json_output:
        click.echo(json.dumps(results, indent=2))
        return

    console.print("[bold green]=== AcreEdge Valuation Results ===[/bold green]")
    for k, v in results.items():
        console.print(f"{k}: [bold cyan]{v}[/bold cyan]")


@cli.command("underwrite")
@click.argument("parcel_id", default="100-204-55A")
@click.option("--json-output", is_flag=True, help="Emit JSON output.")
def underwrite_cmd(parcel_id: str, json_output: bool) -> None:
    """Execute autonomous multi-agent underwriting due diligence on a parcel."""
    orchestrator = SwarmOrchestrator()
    audit = orchestrator.run_due_diligence(parcel_id)

    if json_output:
        click.echo(json.dumps(audit, indent=2))
        return

    console.print(f"[bold cyan]=== Underwriting Due Diligence: {parcel_id} ===[/bold cyan]")
    status_color = "green" if audit.get("overall_status") == "APPROVED" else "red"
    console.print(
        f"Overall Status: [bold {status_color}]{audit.get('overall_status')}[/bold {status_color}]"
    )

    for agent_audit in audit.get("agent_audits", []):
        role = agent_audit.get("agent_role", "")
        status = agent_audit.get("status", "")
        findings = agent_audit.get("findings", "")
        console.print(f"  - [{role}] ({status}): {findings}")


@cli.command("rag-search")
@click.argument("query")
@click.option("--top-k", type=int, default=5, help="Maximum results to return.")
@click.option("--json-output", is_flag=True, help="Emit JSON output.")
def rag_search_cmd(query: str, top_k: int, json_output: bool) -> None:
    """Query hybrid pgvector and Graph-RAG knowledge base."""
    rag = HybridRAGEngine()
    rag.index_document(
        doc_id="DEED-2026-001",
        content="Commercial conveyance deed for 100 Main St, parcel 100-204-55A.",
        metadata={"parcel_id": "100-204-55A"},
    )
    rag.add_graph_relation("DEED-2026-001", "TRANSFERS_PARCEL", "100-204-55A")

    results = rag.hybrid_search(query, top_k=top_k)

    if json_output:
        click.echo(json.dumps(results, indent=2))
        return

    console.print(f"[bold magenta]=== Hybrid RAG Results for: '{query}' ===[/bold magenta]")
    for r in results:
        score = r.get("score", 0.0)
        console.print(f"- [bold cyan]{r['doc_id']}[/bold cyan] (Score: {score}): {r['content']}")
        if r.get("graph_neighbors"):
            console.print(f"  Graph Neighbors: [yellow]{', '.join(r['graph_neighbors'])}[/yellow]")


@cli.command("db-init")
@click.option("--json-output", is_flag=True, help="Emit JSON output.")
def db_init_cmd(json_output: bool) -> None:
    """Initialize PostgreSQL schema, tables, and vector/spatial extensions."""
    mgr = DatabaseManager()
    mgr.connect()
    success = mgr.initialize_schema()
    payload = {
        "connected": mgr.is_connected(),
        "schema_initialized": success,
        "database": mgr.settings.name,
        "host": mgr.settings.host,
        "port": mgr.settings.port,
        "extensions": ["vector", "postgis"],
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    console.print("[bold green]=== PostgreSQL Schema Initialized ===[/bold green]")
    console.print(
        f"Database: [cyan]{mgr.settings.name}[/cyan] at {mgr.settings.host}:{mgr.settings.port}"
    )
    console.print(f"Schema Status: [bold green]{'SUCCESS' if success else 'FAILED'}[/bold green]")
    console.print("Extensions: [magenta]vector, postgis[/magenta]")


@cli.command("serve-mcp")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Inspect registered tools without starting server listener.",
)
def serve_mcp_cmd(dry_run: bool) -> None:
    """Inspect or start custom AcreEdge MCP server."""
    server = AcreEdgeMCPServer()
    tools = list(server.get_registered_tools().keys())
    console.print("[bold cyan]=== AcreEdge Model Context Protocol (MCP) Server ===[/bold cyan]")
    console.print(f"Host: [yellow]{server.settings.host}:{server.settings.port}[/yellow]")
    console.print(f"Registered Tools: [green]{', '.join(tools)}[/green]")
    if not dry_run:
        server.start()
        console.print("[bold green]MCP Server running.[/bold green]")


if __name__ == "__main__":
    cli()
