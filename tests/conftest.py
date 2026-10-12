"""Shared pytest fixtures for AcreEdge test suite."""

from __future__ import annotations

from typing import Any, Dict, List
import pytest

from acreedge.config import AcreEdgeSettings
from acreedge.db.manager import DatabaseManager
from acreedge.mcp.server import AcreEdgeMCPServer
from acreedge.valuation.engine import ValuationEngine
from acreedge.agents.orchestrator import SwarmOrchestrator


@pytest.fixture
def default_settings() -> AcreEdgeSettings:
    """Fixture providing default AcreEdge settings."""
    return AcreEdgeSettings()


@pytest.fixture
def db_manager(default_settings: AcreEdgeSettings) -> DatabaseManager:
    """Fixture providing initialized database manager."""
    mgr = DatabaseManager(default_settings.db)
    mgr.connect()
    return mgr


@pytest.fixture
def mcp_server(default_settings: AcreEdgeSettings) -> AcreEdgeMCPServer:
    """Fixture providing AcreEdge MCP server instance."""
    return AcreEdgeMCPServer(default_settings.mcp)


@pytest.fixture
def valuation_engine() -> ValuationEngine:
    """Fixture providing ValuationEngine instance."""
    return ValuationEngine()


@pytest.fixture
def swarm_orchestrator(default_settings: AcreEdgeSettings) -> SwarmOrchestrator:
    """Fixture providing initialized SwarmOrchestrator instance."""
    return SwarmOrchestrator(default_settings.swarm)


@pytest.fixture
def sample_raw_deed_records() -> List[Dict[str, Any]]:
    """Sample raw municipal deed export records for validation tests."""
    return [
        {
            "parcel_id": "100-204-55A",
            "grantor": "Apex Holdings LLC",
            "grantee": "Meridian Realty Partners",
            "sale_date": "2026-03-15",
            "sale_price_raw": "$4,250,000.00",
            "deed_type": "SPECIAL_WARRANTY",
            "book_page": "B204/P88",
        },
        {
            "parcel_id": "100-204-55B",
            "grantor": "John Doe Trust",
            "grantee": "John Doe Trust",  # non-arm's length
            "sale_date": "2026-04-01",
            "sale_price_raw": "$10.00",  # below minimum price
            "deed_type": "QUITCLAIM",
            "book_page": "B204/P90",
        },
        {
            "parcel_id": "",  # missing parcel id (invalid)
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
            "deed_type": "WARRANTY",
            "book_page": "B205/P12",
        },
    ]
