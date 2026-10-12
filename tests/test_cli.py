"""Tests verifying Stage 5/10 CLI and Interface capabilities for AcreEdge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from acreedge.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Fixture providing CliRunner instance."""
    return CliRunner()


def test_cli_help(runner: CliRunner):
    """Verify root CLI help displays command group and subcommands."""
    res = runner.invoke(cli, ["--help"])
    assert res.exit_code == 0
    assert "AcreEdge: Autonomous Underwriting Engine" in res.output
    assert "generate-sql" in res.output
    assert "clean-export" in res.output
    assert "underwrite" in res.output
    assert "valuation" in res.output


def test_cli_version_and_info(runner: CliRunner):
    """Verify version and info output."""
    res_ver = runner.invoke(cli, ["version"])
    assert res_ver.exit_code == 0
    assert "AcreEdge" in res_ver.output
    assert "v0.1.0" in res_ver.output

    res_info = runner.invoke(cli, ["info"])
    assert res_info.exit_code == 0
    assert "AcreEdge System Summary" in res_info.output
    assert "PostgreSQL DB" in res_info.output
    assert "Underwriting Swarm Agents" in res_info.output


def test_cli_validate_config(runner: CliRunner):
    """Verify configuration validation outputs valid JSON."""
    res = runner.invoke(cli, ["validate-config"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["project_name"] == "AcreEdge"
    assert data["db"]["name"] == "acreedge_db"


def test_cli_generate_sql_kinds(runner: CliRunner):
    """Verify generate-sql options for ddl, clean, quarantine, audit, pipeline, and spatial."""
    # Default (all)
    res_all = runner.invoke(cli, ["generate-sql"])
    assert res_all.exit_code == 0
    assert "CREATE TABLE IF NOT EXISTS validated_deeds" in res_all.output

    # DDL
    res_ddl = runner.invoke(cli, ["generate-sql", "--kind", "ddl"])
    assert res_ddl.exit_code == 0
    assert "CREATE TABLE IF NOT EXISTS raw_municipal_deeds" in res_ddl.output
    assert "CREATE TABLE IF NOT EXISTS validated_deeds" in res_ddl.output

    # Clean
    res_clean = runner.invoke(cli, ["generate-sql", "--kind", "clean"])
    assert res_clean.exit_code == 0
    assert "INSERT INTO validated_deeds" in res_clean.output

    # Quarantine
    res_quar = runner.invoke(cli, ["generate-sql", "--kind", "quarantine"])
    assert res_quar.exit_code == 0
    assert "INSERT INTO quarantined_deeds" in res_quar.output
    assert "MISSING_PARCEL_ID" in res_quar.output

    # Audit
    res_audit = runner.invoke(cli, ["generate-sql", "--kind", "audit"])
    assert res_audit.exit_code == 0
    assert "SELECT COUNT(*) FROM raw_municipal_deeds" in res_audit.output

    # Pipeline
    res_pipe = runner.invoke(cli, ["generate-sql", "--kind", "pipeline"])
    assert res_pipe.exit_code == 0
    assert "BEGIN;" in res_pipe.output
    assert "COMMIT;" in res_pipe.output

    # Spatial
    res_spatial = runner.invoke(
        cli,
        [
            "generate-sql",
            "--kind",
            "spatial",
            "--lat",
            "40.7128",
            "--lon",
            "-74.0060",
            "--radius",
            "3.5",
        ],
    )
    assert res_spatial.exit_code == 0
    assert "ST_DWithin" in res_spatial.output
    assert "ST_MakePoint(-74.006, 40.7128)" in res_spatial.output


def test_cli_clean_export_sample(runner: CliRunner):
    """Verify clean-export command with default sample deeds."""
    res = runner.invoke(cli, ["clean-export"])
    assert res.exit_code == 0
    assert "Deed Export Validation Batch" in res.output
    assert "Total Records: 4" in res.output
    assert "Valid Arm's-Length: 2" in res.output
    assert "100-204-55A" in res.output


def test_cli_clean_export_json_and_custom_file(runner: CliRunner, tmp_path: Path):
    """Verify clean-export with custom file input and JSON serialization."""
    records = [
        {
            "parcel_id": "200-ABC-11",
            "grantor": "Alpha LLC",
            "grantee": "Beta Corp",
            "sale_date": "2026-05-01",
            "sale_price_raw": "$3,000,000",
            "deed_type": "WARRANTY DEED",
        },
        {
            "parcel_id": "200-ABC-12",
            "grantor": "Self Trust",
            "grantee": "Self Trust",
            "sale_date": "2026-05-02",
            "sale_price_raw": "$1.00",
            "deed_type": "QUITCLAIM",
        },
    ]
    file_path = tmp_path / "deeds_test.json"
    file_path.write_text(json.dumps(records), encoding="utf-8")

    res = runner.invoke(cli, ["clean-export", "--file", str(file_path), "--json-output"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["total"] == 2
    assert data["valid_count"] == 1
    assert data["invalid_count"] == 1
    assert data["valid_records"][0]["parcel_id"] == "200-ABC-11"


def test_cli_ingest(runner: CliRunner):
    """Verify ingest command execution and JSON flags."""
    res = runner.invoke(cli, ["ingest", "--source", "parcels_q1.csv", "--run-cleaning"])
    assert res.exit_code == 0
    assert "Municipal Deed Ingestion Pipeline" in res.output
    assert "parcels_q1.csv" in res.output

    res_json = runner.invoke(
        cli,
        ["ingest", "--source", "parcels_q1.csv", "--run-cleaning", "--json-output"],
    )
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["staging"]["status"] == "STAGED"
    assert data["cleaning"]["status"] == "SUCCESS"


def test_cli_valuation(runner: CliRunner):
    """Verify valuation CLI calculations for direct cap, sqft, and DCF."""
    # Direct cap
    res = runner.invoke(
        cli,
        [
            "valuation",
            "--noi",
            "150000",
            "--cap-rate",
            "0.06",
            "--square-feet",
            "20000",
        ],
    )
    assert res.exit_code == 0
    assert "direct_cap_valuation: 2500000.0" in res.output
    assert "value_per_sqft: 125.0" in res.output

    # Cap rate calculation from property value
    res_cap = runner.invoke(
        cli,
        [
            "valuation",
            "--noi",
            "120000",
            "--property-value",
            "2000000",
            "--json-output",
        ],
    )
    assert res_cap.exit_code == 0
    data = json.loads(res_cap.output)
    assert data["calculated_cap_rate"] == 0.06

    # DCF
    res_dcf = runner.invoke(
        cli,
        [
            "valuation",
            "--cash-flows",
            "10000,10000,10000",
            "--discount-rate",
            "0.10",
            "--terminal-value",
            "100000",
            "--json-output",
        ],
    )
    assert res_dcf.exit_code == 0
    dcf_data = json.loads(res_dcf.output)
    assert dcf_data["dcf_valuation"] > 0


def test_cli_underwrite(runner: CliRunner):
    """Verify underwriting due diligence command."""
    res = runner.invoke(cli, ["underwrite", "100-204-55A"])
    assert res.exit_code == 0
    assert "Underwriting Due Diligence: 100-204-55A" in res.output
    assert "APPROVED" in res.output
    assert "DeedAuditor" in res.output

    res_json = runner.invoke(cli, ["underwrite", "100-204-55A", "--json-output"])
    assert res_json.exit_code == 0
    audit_data = json.loads(res_json.output)
    assert audit_data["parcel_id"] == "100-204-55A"
    assert audit_data["overall_status"] == "APPROVED"
    assert len(audit_data["agent_audits"]) == 4


def test_cli_rag_search(runner: CliRunner):
    """Verify hybrid RAG search command."""
    res = runner.invoke(cli, ["rag-search", "100 Main St"])
    assert res.exit_code == 0
    assert "Hybrid RAG Results" in res.output
    assert "DEED-2026-001" in res.output

    res_json = runner.invoke(cli, ["rag-search", "100 Main St", "--json-output"])
    assert res_json.exit_code == 0
    rag_data = json.loads(res_json.output)
    assert len(rag_data) >= 1
    assert rag_data[0]["doc_id"] == "DEED-2026-001"


def test_cli_db_init(runner: CliRunner):
    """Verify database initialization command."""
    res = runner.invoke(cli, ["db-init"])
    assert res.exit_code == 0
    assert "PostgreSQL Schema Initialized" in res.output
    assert "SUCCESS" in res.output

    res_json = runner.invoke(cli, ["db-init", "--json-output"])
    assert res_json.exit_code == 0
    db_data = json.loads(res_json.output)
    assert db_data["connected"] is True
    assert db_data["schema_initialized"] is True


def test_cli_serve_mcp(runner: CliRunner):
    """Verify MCP server inspection and start dry-run."""
    res = runner.invoke(cli, ["serve-mcp", "--dry-run"])
    assert res.exit_code == 0
    assert "AcreEdge Model Context Protocol" in res.output
    assert "calculate_valuation" in res.output
    assert "query_validated_deeds" in res.output
    assert "underwrite_property" in res.output
