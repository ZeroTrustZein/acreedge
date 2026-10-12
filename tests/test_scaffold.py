"""Comprehensive test suite verifying Stage 1/10 scaffolding for AcreEdge."""

from __future__ import annotations

from typing import Any, Dict, List
from click.testing import CliRunner

from acreedge import __author__, __version__
from acreedge.config import AcreEdgeSettings
from acreedge.cli import cli
from acreedge.db.manager import DatabaseManager
from acreedge.db.sql_validator import SQLRawExportValidator
from acreedge.ingestion.pipeline import MunicipalDeedIngestionPipeline
from acreedge.mcp.server import AcreEdgeMCPServer
from acreedge.rag.engine import HybridRAGEngine
from acreedge.valuation.engine import ValuationEngine
from acreedge.agents.orchestrator import SwarmOrchestrator, UnderwritingAgent
from acreedge.protocols import (
    DatabaseManagerProtocol,
    RawExportValidatorProtocol,
    MunicipalDeedIngestionProtocol,
    MCPServerProtocol,
    ValuationModelProtocol,
    HybridRAGProtocol,
    SwarmAgentProtocol,
    SwarmOrchestratorProtocol,
)


def test_package_metadata():
    """Verify package version and author attributes."""
    assert __version__ == "0.1.0"
    assert __author__ == "Zein"


def test_settings_defaults(default_settings: AcreEdgeSettings):
    """Verify default configurations across all subsystems."""
    assert default_settings.project_name == "AcreEdge"
    assert default_settings.version == "0.1.0"
    assert default_settings.environment == "development"
    assert default_settings.db.host == "localhost"
    assert default_settings.db.port == 5432
    assert default_settings.db.name == "acreedge_db"
    assert "postgresql://" in default_settings.db.connection_string
    assert default_settings.mcp.port == 8440
    assert default_settings.rag.vector_dim == 1536
    assert default_settings.ingestion.min_sale_price == 100.0
    assert default_settings.swarm.max_concurrent_agents == 4
    assert "DeedAuditor" in default_settings.swarm.roles


def test_protocol_implementations(
    db_manager: DatabaseManager,
    mcp_server: AcreEdgeMCPServer,
    valuation_engine: ValuationEngine,
    swarm_orchestrator: SwarmOrchestrator,
):
    """Verify runtime checkable protocols adherence."""
    validator = SQLRawExportValidator()
    pipeline = MunicipalDeedIngestionPipeline()
    rag = HybridRAGEngine()
    agent = UnderwritingAgent("DeedAuditor")

    assert isinstance(db_manager, DatabaseManagerProtocol)
    assert isinstance(validator, RawExportValidatorProtocol)
    assert isinstance(pipeline, MunicipalDeedIngestionProtocol)
    assert isinstance(mcp_server, MCPServerProtocol)
    assert isinstance(valuation_engine, ValuationModelProtocol)
    assert isinstance(rag, HybridRAGProtocol)
    assert isinstance(agent, SwarmAgentProtocol)
    assert isinstance(swarm_orchestrator, SwarmOrchestratorProtocol)


def test_sql_validator_ddl_and_sql():
    """Verify PostgreSQL SQL queries generated for cleaning raw municipal deed exports."""
    validator = SQLRawExportValidator()
    ddl = validator.generate_schema_ddl()
    sql = validator.generate_validation_sql()

    assert "CREATE TABLE IF NOT EXISTS raw_municipal_deeds" in ddl
    assert "CREATE TABLE IF NOT EXISTS validated_deeds" in ddl
    assert "INSERT INTO validated_deeds" in sql
    assert "FROM raw_municipal_deeds" in sql
    assert "REGEXP_REPLACE" in sql
    assert "is_arms_length" in sql


def test_sql_validator_batch_cleaning(sample_raw_deed_records: List[Dict[str, Any]]):
    """Verify in-memory cleaning and filtering of raw deed exports."""
    validator = SQLRawExportValidator()
    result = validator.validate_batch(sample_raw_deed_records)

    assert result["total"] == 4
    # 1 valid arm's-length ($4.25M), 1 valid arm's-length ($1.85M)
    # 1 invalid (< $100 price), 1 invalid (empty parcel ID)
    assert result["valid_count"] == 2
    assert result["invalid_count"] == 2

    valid_parcels = [r["parcel_id"] for r in result["valid_records"]]
    assert "100-204-55A" in valid_parcels
    assert "100-204-56C" in valid_parcels


def test_ingestion_pipeline(sample_raw_deed_records: List[Dict[str, Any]]):
    """Verify municipal deed ingestion pipeline."""
    pipeline = MunicipalDeedIngestionPipeline()
    res = pipeline.process_records(sample_raw_deed_records)
    assert res["valid_count"] == 2
    assert "INSERT INTO validated_deeds" in pipeline.get_ingestion_sql()


def test_database_manager(db_manager: DatabaseManager):
    """Verify database manager lifecycle and query execution."""
    assert db_manager.is_connected() is True
    assert db_manager.initialize_schema() is True
    query_res = db_manager.execute_query("SELECT 1;")
    assert query_res == [{"status": 1}]
    db_manager.disconnect()
    assert db_manager.is_connected() is False


def test_mcp_server(mcp_server: AcreEdgeMCPServer):
    """Verify custom MCP server tool registrations and execution."""
    tools = mcp_server.get_registered_tools()
    assert "calculate_valuation" in tools
    assert "query_validated_deeds" in tools
    assert "underwrite_property" in tools

    mcp_server.start()
    assert mcp_server.is_running() is True

    # Test valuation tool execution
    val_handler = tools["calculate_valuation"]
    val_res = val_handler(noi=100000.0, cap_rate=0.05)
    assert val_res["estimated_value"] == 2000000.0

    mcp_server.stop()
    assert mcp_server.is_running() is False


def test_valuation_engine(valuation_engine: ValuationEngine):
    """Verify valuation calculations including cap rate and DCF."""
    cap_rate = valuation_engine.calculate_cap_rate(noi=60000.0, property_value=1000000.0)
    assert cap_rate == 0.06

    val_res = valuation_engine.calculate_valuation({
        "noi": 120000.0,
        "cap_rate": 0.06,
        "square_feet": 15000.0,
    })
    assert val_res["estimated_value"] == 2000000.0
    assert val_res["value_per_sqft"] == 133.33

    # DCF test
    dcf_val = valuation_engine.calculate_dcf(
        cash_flows=[10000.0, 10000.0, 10000.0],
        discount_rate=0.10,
        terminal_value=100000.0,
    )
    assert dcf_val > 0


def test_hybrid_rag_engine():
    """Verify hybrid pgvector and Graph-RAG engine."""
    rag = HybridRAGEngine()
    indexed = rag.index_document(
        doc_id="DEED-2026-001",
        content="Commercial conveyance deed for 100 Main St.",
        metadata={"parcel_id": "100-204-55A"},
    )
    assert indexed is True

    rag.add_graph_relation("DEED-2026-001", "TRANSFERS_PARCEL", "100-204-55A")
    results = rag.hybrid_search("100 Main St", top_k=1)
    assert len(results) == 1
    assert results[0]["doc_id"] == "DEED-2026-001"
    assert "100-204-55A" in results[0]["graph_neighbors"]


def test_swarm_orchestrator(swarm_orchestrator: SwarmOrchestrator):
    """Verify multi-agent underwriting coordinator and audits."""
    agents = swarm_orchestrator.get_registered_agents()
    assert len(agents) == 4
    assert "DeedAuditor" in agents
    assert "ValuationSpecialist" in agents

    audit = swarm_orchestrator.run_due_diligence("100-204-55A")
    assert audit["parcel_id"] == "100-204-55A"
    assert audit["overall_status"] == "APPROVED"
    assert len(audit["agent_audits"]) == 4


def test_cli_commands():
    """Verify CLI entrypoint commands execute successfully."""
    runner = CliRunner()

    res_version = runner.invoke(cli, ["version"])
    assert res_version.exit_code == 0
    assert "AcreEdge" in res_version.output
    assert "0.1.0" in res_version.output

    res_info = runner.invoke(cli, ["info"])
    assert res_info.exit_code == 0
    assert "AcreEdge System Summary" in res_info.output
    assert "PostgreSQL DB" in res_info.output

    res_config = runner.invoke(cli, ["validate-config"])
    assert res_config.exit_code == 0
    assert "acreedge_db" in res_config.output

    res_sql = runner.invoke(cli, ["generate-sql"])
    assert res_sql.exit_code == 0
    assert "CREATE TABLE IF NOT EXISTS validated_deeds" in res_sql.output
