"""Tests verifying Stage 2/10 types and domain models for AcreEdge."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError as PydanticValidationError

from acreedge.db.sql_validator import SQLRawExportValidator
from acreedge.types import (
    AgentRole,
    CleanDeedRecord,
    DCFAnalysis,
    DeedType,
    GraphRelation,
    MCPToolCall,
    MCPToolResult,
    PropertyType,
    RAGDocument,
    RAGSearchResult,
    RawDeedRecord,
    UnderwritingFinding,
    UnderwritingReport,
    UnderwritingStatus,
    ValidationBatchResult,
    ValidationError,
    ValuationInput,
    ValuationResult,
)
from acreedge.valuation.engine import ValuationEngine


def test_deed_type_enumeration():
    """Verify standard deed type enum variants."""
    assert DeedType.DEED == "DEED"
    assert DeedType.WARRANTY_DEED == "WARRANTY DEED"
    assert DeedType.QUITCLAIM == "QUITCLAIM"
    assert DeedType.SPECIAL_WARRANTY == "SPECIAL WARRANTY"
    assert DeedType.TAX_DEED == "TAX DEED"


def test_raw_deed_record():
    """Verify raw deed record ingestion schema."""
    raw = RawDeedRecord(
        parcel_id="100-204-55A",
        grantor="Seller Corp",
        grantee="Buyer LLC",
        sale_date="2026-04-15",
        sale_price_raw="$2,450,000.00",
    )
    assert raw.parcel_id == "100-204-55A"
    assert raw.sale_price_raw == "$2,450,000.00"
    assert raw.deed_type == "DEED"
    assert raw.raw_id is None


def test_clean_deed_record_normalization():
    """Verify parcel_id uppercasing and ISO sale_date parsing."""
    clean = CleanDeedRecord(
        parcel_id="  100-204-55a  ",
        grantor="Seller Corp",
        grantee="Buyer LLC",
        sale_date="2026-04-15",
        sale_price=2450000.0,
    )
    assert clean.parcel_id == "100-204-55A"
    assert clean.sale_date == date(2026, 4, 15)
    assert clean.sale_price == 2450000.0
    assert clean.is_arms_length is True


def test_clean_deed_record_validation_errors():
    """Verify invalid fields trigger validation errors."""
    with pytest.raises(PydanticValidationError):
        CleanDeedRecord(
            parcel_id="",
            grantor="Seller",
            grantee="Buyer",
            sale_date="2026-04-15",
            sale_price=100.0,
        )

    with pytest.raises(PydanticValidationError):
        CleanDeedRecord(
            parcel_id="100-ABC",
            grantor="Seller",
            grantee="Buyer",
            sale_date="invalid-date",
            sale_price=100.0,
        )

    with pytest.raises(PydanticValidationError):
        CleanDeedRecord(
            parcel_id="100-ABC",
            grantor="Seller",
            grantee="Buyer",
            sale_date="2026-04-15",
            sale_price=-500.0,
        )


def test_validation_error_and_batch_result():
    """Verify batch validation result schema."""
    err = ValidationError(
        record_index=0,
        parcel_id="BAD-001",
        field="sale_price",
        message="Below minimum threshold",
    )
    batch = ValidationBatchResult(
        total_records=10,
        valid_records=8,
        rejected_records=2,
        pass_rate=0.8,
        errors=[err],
        cleaned_records=[],
    )
    assert batch.total_records == 10
    assert batch.pass_rate == 0.8
    assert len(batch.errors) == 1


def test_sql_validator_with_models():
    """Verify SQLRawExportValidator integration with domain models."""
    validator = SQLRawExportValidator()

    records = [
        {
            "parcel_id": "100-204-55A",
            "grantor": "Apex Holdings LLC",
            "grantee": "Meridian Realty Partners",
            "sale_date": "2026-04-15",
            "sale_price_raw": "$2,450,000.00",
            "deed_type": "WARRANTY DEED",
        },
        {
            "parcel_id": "100-204-56B",
            "grantor": "UNKNOWN",
            "grantee": "Unknown LLC",
            "sale_date": "2026-04-20",
            "sale_price_raw": "$0.00",
        },
    ]

    res = validator.validate_batch_models(records)
    assert res.total_records == 2
    assert res.valid_records == 1
    assert res.rejected_records == 1
    assert res.pass_rate == 0.5
    assert len(res.cleaned_records) == 1
    assert res.cleaned_records[0].parcel_id == "100-204-55A"
    assert res.cleaned_records[0].sale_price == 2450000.0
    assert len(res.errors) == 1


def test_valuation_types_and_engine():
    """Verify valuation inputs, results, and engine integration."""
    engine = ValuationEngine()
    inp = ValuationInput(
        parcel_id="100-204-55A",
        noi=120_000.0,
        cap_rate=0.06,
        square_feet=10_000.0,
        property_type=PropertyType.COMMERCIAL,
    )
    assert inp.property_type == PropertyType.COMMERCIAL

    result: ValuationResult = engine.evaluate(inp)
    assert result.parcel_id == "100-204-55A"
    assert result.estimated_value == 2000000.0
    assert result.value_per_sqft == 200.0
    assert result.confidence_score == 0.92

    dcf: DCFAnalysis = engine.evaluate_dcf([10000.0, 12000.0, 15000.0], 0.08, 100000.0)
    assert dcf.discount_rate == 0.08
    assert dcf.npv > 0


def test_rag_and_graph_types():
    """Verify RAG document and graph relation schemas."""
    doc = RAGDocument(
        doc_id="doc_1",
        content="Deed book 452 page 12 recorded at municipal registry.",
        metadata={"parcel_id": "100-204-55A"},
    )
    assert doc.doc_id == "doc_1"

    rel = GraphRelation(
        source="Apex Holdings LLC",
        relation="TRANSFER_TO",
        target="Meridian Realty Partners",
        weight=1.0,
    )
    assert rel.relation == "TRANSFER_TO"

    hit = RAGSearchResult(
        doc_id="doc_1",
        content=doc.content,
        score=0.88,
        graph_relevance=0.95,
    )
    assert hit.score == 0.88
    assert hit.graph_relevance == 0.95


def test_swarm_and_mcp_types():
    """Verify swarm underwriting and MCP tool call models."""
    finding = UnderwritingFinding(
        agent_role=AgentRole.LEGAL,
        category="title_chain",
        severity="INFO",
        description="Clean title chain observed.",
        score=0.98,
    )
    report = UnderwritingReport(
        parcel_id="100-204-55A",
        status=UnderwritingStatus.APPROVED,
        overall_risk_score=12.5,
        findings=[finding],
        summary="Low risk acquisition candidate.",
    )
    assert report.status == UnderwritingStatus.APPROVED
    assert len(report.findings) == 1

    call = MCPToolCall(name="evaluate_parcel", arguments={"parcel_id": "100-204-55A"})
    res = MCPToolResult(tool="evaluate_parcel", content={"estimated_value": 2000000.0})
    assert call.name == "evaluate_parcel"
    assert res.is_error is False
