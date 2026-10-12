"""AcreEdge: Autonomous Multi-Agent Underwriting Engine and Municipal Deed Ingestion."""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Zein"

from acreedge.config import AcreEdgeSettings
from acreedge.types import (
    AgentRole,
    CleanDeedRecord,
    DeedType,
    RawDeedRecord,
    UnderwritingReport,
    ValuationInput,
    ValuationResult,
)

__all__ = [
    "__version__",
    "__author__",
    "AcreEdgeSettings",
    "AgentRole",
    "CleanDeedRecord",
    "DeedType",
    "RawDeedRecord",
    "UnderwritingReport",
    "ValuationInput",
    "ValuationResult",
]
