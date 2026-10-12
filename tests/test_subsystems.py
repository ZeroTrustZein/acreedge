"""Comprehensive test suite verifying Stage 4/10 Subsystems for AcreEdge."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from acreedge.config import AcreEdgeSettings
from acreedge.db.manager import DatabaseManager
from acreedge.db.sql_validator import SQLRawExportValidator
from acreedge.ingestion.pipeline import MunicipalDeedIngestionPipeline
from acreedge.mcp.server import AcreEdgeMCPServer
from acreedge.rag.engine import HybridRAGEngine
from acreedge.types import (
    CleanDeedRecord,
    MCPToolCall,
    MCPToolResult,
    UnderwritingReport,
    UnderwritingStatus,
    ValidationBatchResult,
)
from acreedge.valuation.engine import ValuationEngine


def test_sql_validator_quarantine_and_audit():
    """Verify quarantine and audit SQL queries generated for PostgreSQL."""
    validator = SQLRawExportValidator()
    ddl = validator.generate_schema_ddl()
    quarantine_sql = validator.generate_quarantine_sql()
    audit_sql = validator.generate_audit_sql()
    pipeline_sql = validator.build_pipeline_sql()

    assert "CREATE TABLE IF NOT EXISTS quarantined_deeds" in ddl
    assert "INSERT INTO quarantined_deeds" in quarantine_sql
    assert "MISSING_PARCEL_ID" in quarantine_sql
    assert "PRICE_BELOW_MINIMUM" in quarantine_sql
    assert "NON_ARMS_LENGTH_TRANSFER" in quarantine_sql
    assert "SELECT COUNT(*) FROM raw_municipal_deeds" in audit_sql
    assert "BEGIN;" in pipeline_sql
    assert "COMMIT;" in pipeline_sql


def test_sql_validator_spatial_comps():
    """Verify PostGIS query generation for spatial comps."""
    validator = SQLRawExportValidator()
    spatial_sql = validator.generate_spatial_comps_sql(
        latitude=40.7128, longitude=-74.0060, radius_miles=3.0
    )

    assert "ST_DWithin" in spatial_sql
    assert "ST_Distance" in spatial_sql
    assert "ST_MakePoint(-74.006, 40.7128)" in spatial_sql
    assert "is_arms_length = TRUE" in spatial_sql
    assert "distance_miles ASC" in spatial_sql


def test_database_manager_subsystem(db_manager: DatabaseManager):
    """Verify DatabaseManager spatial queries, ping, and mock execution."""
    ping_info = db_manager.ping()
    assert ping_info["connected"] is True
    assert ping_info["port"] == 5432
    assert ping_info["database"] == "acreedge_db"

    spatial_sql = db_manager.get_spatial_comps_sql(37.7749, -122.4194, radius_miles=2.5)
    assert "ST_DWithin" in spatial_sql
    assert "validated_deeds" in spatial_sql

    count_res = db_manager.execute_query("SELECT COUNT(*) FROM raw_municipal_deeds;")
    assert len(count_res) == 1
    assert count_res[0]["total_validated"] == 8


def test_ingestion_pipeline_subsystem(
    db_manager: DatabaseManager, sample_raw_deed_records: List[Dict[str, Any]]
):
    """Verify MunicipalDeedIngestionPipeline batch models and cleaning execution."""
    pipeline = MunicipalDeedIngestionPipeline(db_manager=db_manager)

    batch_res = pipeline.process_batch_models(sample_raw_deed_records)
    assert isinstance(batch_res, ValidationBatchResult)
    assert batch_res.total_records == len(sample_raw_deed_records)
    assert batch_res.valid_records >= 2

    clean_res = pipeline.run_cleaning_pipeline()
    assert clean_res["status"] == "SUCCESS"
    assert clean_res["sql_applied"] is True
    assert "BEGIN;" in clean_res["pipeline_sql"]

    assert "INSERT INTO validated_deeds" in pipeline.get_pipeline_sql()


def test_valuation_engine_comps_and_blended(valuation_engine: ValuationEngine):
    """Verify ValuationEngine sales comps calculation and fallbacks."""
    comps = [
        CleanDeedRecord(
            parcel_id="101-A",
            grantor="Party A",
            grantee="Party B",
            sale_date="2026-01-01",
            sale_price=1200000.0,
        ),
        CleanDeedRecord(
            parcel_id="101-B",
            grantor="Party C",
            grantee="Party D",
            sale_date="2026-02-01",
            sale_price=1400000.0,
        ),
    ]

    comps_result = valuation_engine.calculate_comps_valuation(comps)
    assert comps_result["comp_count"] == 2
    assert comps_result["estimated_value"] == 1300000.0

    # Test valuation when NOI is zero, falling back to comps
    val_res = valuation_engine.calculate_valuation(
        {
            "parcel_id": "TARGET-001",
            "noi": 0.0,
            "square_feet": 10000.0,
            "comps": comps,
        }
    )
    assert val_res["parcel_id"] == "TARGET-001"
    assert val_res["estimated_value"] == 1300000.0
    assert val_res["value_per_sqft"] == 130.0


def test_hybrid_rag_chain_of_title():
    """Verify HybridRAGEngine deed lineage and typed search results."""
    rag = HybridRAGEngine()
    rag.index_document(
        doc_id="PARCEL-404",
        content="Commercial warehouse in Southside industrial park.",
        metadata={"sqft": 45000},
    )

    rag.add_graph_relation("SELLER-CORP", "CONVEYED_VIA_DEED", "BUYER-LLC")
    rag.add_graph_relation("PARCEL-404", "SUBJECT_OF", "SELLER-CORP")

    lineage = rag.get_chain_of_title("PARCEL-404")
    assert len(lineage) == 1
    assert lineage[0]["relation"] == "SUBJECT_OF"

    models = rag.search_models("industrial park", top_k=2)
    assert len(models) == 1
    assert models[0].doc_id == "PARCEL-404"
    assert models[0].score == 0.88


def test_swarm_orchestrator_due_diligence_report(default_settings: AcreEdgeSettings):
    """Verify SwarmOrchestrator generates typed UnderwritingReport."""
    from acreedge.agents.orchestrator import SwarmOrchestrator

    orchestrator = SwarmOrchestrator(default_settings.swarm)
    report = orchestrator.run_due_diligence_report("PARCEL-999", purchase_price=5000000.0)

    assert isinstance(report, UnderwritingReport)
    assert report.parcel_id == "PARCEL-999"
    assert report.status == UnderwritingStatus.APPROVED
    assert report.overall_risk_score == 15.0
    assert len(report.findings) == len(default_settings.swarm.roles)


def test_mcp_server_call_tool(mcp_server: AcreEdgeMCPServer):
    """Verify AcreEdgeMCPServer processes MCPToolCall into MCPToolResult."""
    # Test valid call
    call = MCPToolCall(
        name="calculate_valuation",
        arguments={"noi": 150000.0, "cap_rate": 0.06},
    )
    result = mcp_server.call_tool(call)
    assert isinstance(result, MCPToolResult)
    assert result.is_error is False
    assert result.tool == "calculate_valuation"
    assert result.content["estimated_value"] == 2500000.0

    # Test invalid call (error handling)
    bad_call = MCPToolCall(
        name="calculate_valuation",
        arguments={"noi": 150000.0, "cap_rate": 0.0},
    )
    bad_result = mcp_server.call_tool(bad_call)
    assert bad_result.is_error is True
    assert "Cap rate must be greater than zero" in str(bad_result.content)

    # Test unregistered tool
    with pytest.raises(KeyError):
        mcp_server.execute_tool("unknown_tool", {})

    # Test query_validated_deeds tool
    deeds_call = MCPToolCall(name="query_validated_deeds", arguments={"parcel_id": "P-101"})
    deeds_res = mcp_server.call_tool(deeds_call)
    assert deeds_res.is_error is False
    assert deeds_res.content["parcel_id"] == "P-101"

    # Test underwrite_property tool
    uw_call = MCPToolCall(
        name="underwrite_property",
        arguments={"parcel_id": "P-101", "purchase_price": 2000000.0},
    )
    uw_res = mcp_server.call_tool(uw_call)
    assert uw_res.is_error is False
    assert uw_res.content["purchase_price"] == 2000000.0


def test_db_manager_autoconnect_paths():
    """Verify DatabaseManager connects automatically when disconnected."""
    mgr = DatabaseManager()
    assert mgr.is_connected() is False
    assert mgr.initialize_schema() is True
    assert mgr.is_connected() is True

    mgr.disconnect()
    assert mgr.is_connected() is False
    res = mgr.execute_query("SELECT 1;")
    assert res == [{"status": 1}]
    assert mgr.is_connected() is True


def test_valuation_engine_dcf_invalid_discount():
    """Verify ValuationEngine rejects discount rate <= -100%."""
    engine = ValuationEngine()
    with pytest.raises(ValueError, match="Discount rate cannot be <= -100%"):
        engine.calculate_dcf([1000.0], discount_rate=-1.5)


def test_swarm_orchestrator_rejection_flow(default_settings: AcreEdgeSettings):
    """Verify SwarmOrchestrator handles non-APPROVED agent evaluations."""
    from acreedge.agents.orchestrator import SwarmOrchestrator
    from unittest.mock import MagicMock

    orchestrator = SwarmOrchestrator(default_settings.swarm)
    # Mock one agent to return REJECTED
    mock_agent = MagicMock()
    mock_agent.execute_task.return_value = {
        "status": "REJECTED",
        "agent_role": "RiskUnderwriter",
        "findings": "Extreme environmental hazard detected",
    }
    orchestrator.register_agent(mock_agent)

    report = orchestrator.run_due_diligence_report("PARCEL-RISK")
    assert report.status == UnderwritingStatus.REJECTED
    assert report.overall_risk_score == 75.0

