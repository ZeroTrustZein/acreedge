"""Strong domain types and Pydantic schemas for AcreEdge."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# =====================================================================
# Deed & Ingestion Domain Models
# =====================================================================


class DeedType(str, Enum):
    """Recognized deed instrument classifications."""

    DEED = "DEED"
    WARRANTY_DEED = "WARRANTY DEED"
    SPECIAL_WARRANTY = "SPECIAL WARRANTY"
    QUITCLAIM = "QUITCLAIM"
    GRANT_DEED = "GRANT DEED"
    TAX_DEED = "TAX DEED"
    TRUSTEE_DEED = "TRUSTEE DEED"
    EXECUTOR_DEED = "EXECUTOR DEED"
    OTHER = "OTHER"


class RawDeedRecord(BaseModel):
    """Raw deed record imported from municipal staging exports."""

    raw_id: Optional[int] = None
    parcel_id: str = Field(..., description="Municipal parcel / APN identifier")
    grantor: str = Field(default="UNKNOWN", description="Seller or transferring party")
    grantee: str = Field(default="UNKNOWN", description="Buyer or acquiring party")
    sale_date: str = Field(..., description="Raw recorded sale date string")
    sale_price_raw: Optional[str] = Field(default=None, description="Unparsed raw currency string")
    deed_type: str = Field(default="DEED", description="Type of deed instrument")
    book_page: Optional[str] = Field(default=None, description="Registry book/page reference")
    recorded_at: Optional[datetime] = None


class CleanDeedRecord(BaseModel):
    """Validated, normalized, arms-length qualified deed record."""

    deed_id: Optional[int] = None
    parcel_id: str = Field(..., min_length=1, description="Normalized uppercase parcel ID")
    grantor: str = Field(..., min_length=1)
    grantee: str = Field(..., min_length=1)
    sale_date: date = Field(..., description="Parsed standard ISO sale date")
    sale_price: float = Field(..., ge=0.0, description="Cleaned sale consideration")
    deed_type: str = Field(default="DEED")
    book_page: Optional[str] = None
    is_arms_length: bool = Field(default=True, description="Arms-length transaction flag")
    validated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("parcel_id", mode="before")
    @classmethod
    def normalize_parcel_id(cls, v: Any) -> str:
        s = str(v).strip().upper()
        if not s:
            raise ValueError("parcel_id must not be empty")
        return s

    @field_validator("sale_date", mode="before")
    @classmethod
    def parse_sale_date(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            s = v.strip()
            # Handle YYYY-MM-DD or parse date portion
            if "T" in s:
                s = s.split("T")[0]
            return date.fromisoformat(s)
        raise ValueError(f"Invalid date format: {v}")


class ValidationError(BaseModel):
    """Error encountered during municipal export validation."""

    record_index: Optional[int] = None
    parcel_id: Optional[str] = None
    field: str
    message: str
    raw_value: Optional[Any] = None


class ValidationBatchResult(BaseModel):
    """Summary of batch cleaning and validation run."""

    total_records: int = Field(..., ge=0)
    valid_records: int = Field(..., ge=0)
    rejected_records: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    errors: List[ValidationError] = Field(default_factory=list)
    cleaned_records: List[CleanDeedRecord] = Field(default_factory=list)


# =====================================================================
# Valuation Models
# =====================================================================


class PropertyType(str, Enum):
    """Property asset class."""

    COMMERCIAL = "COMMERCIAL"
    RESIDENTIAL = "RESIDENTIAL"
    INDUSTRIAL = "INDUSTRIAL"
    AGRICULTURAL = "AGRICULTURAL"
    MIXED_USE = "MIXED_USE"
    VACANT_LAND = "VACANT_LAND"


class ValuationInput(BaseModel):
    """Input parameters for direct capitalization or comparable valuation."""

    parcel_id: str
    noi: float = Field(ge=0.0, description="Net Operating Income in USD")
    cap_rate: float = Field(default=0.065, gt=0.0, le=1.0, description="Market cap rate")
    square_feet: float = Field(default=1.0, gt=0.0, description="Gross building area")
    property_type: PropertyType = PropertyType.COMMERCIAL
    comps: List[CleanDeedRecord] = Field(default_factory=list)


class ValuationResult(BaseModel):
    """Computed valuation metrics."""

    parcel_id: str
    estimated_value: float = Field(ge=0.0)
    noi: float = Field(ge=0.0)
    cap_rate: float = Field(gt=0.0)
    value_per_sqft: float = Field(ge=0.0)
    confidence_score: float = Field(default=0.92, ge=0.0, le=1.0)


class DCFAnalysis(BaseModel):
    """Discounted Cash Flow calculation model."""

    cash_flows: List[float]
    discount_rate: float = Field(gt=-1.0, description="Discount rate")
    terminal_value: float = Field(default=0.0, ge=0.0)
    npv: float


# =====================================================================
# Hybrid RAG & Knowledge Graph Models
# =====================================================================


class RAGDocument(BaseModel):
    """Indexed document chunk for dense retrieval."""

    doc_id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None


class GraphRelation(BaseModel):
    """Knowledge graph relation between deed entities."""

    source: str
    relation: str
    target: str
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RAGSearchResult(BaseModel):
    """Hybrid search retrieved hit combining dense and graph signals."""

    doc_id: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    graph_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =====================================================================
# Swarm Underwriting & Multi-Agent Models
# =====================================================================


class AgentRole(str, Enum):
    """Specialized swarm agent persona roles."""

    ORCHESTRATOR = "orchestrator"
    LEGAL = "legal"
    FINANCIAL = "financial"
    ENVIRONMENTAL = "environmental"
    ZONING = "zoning"


class UnderwritingStatus(str, Enum):
    """Outcome status for parcel underwriting."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"


class UnderwritingFinding(BaseModel):
    """Individual agent assessment finding."""

    agent_role: AgentRole
    category: str
    severity: str = Field(default="INFO", pattern="^(INFO|WARNING|CRITICAL)$")
    description: str
    score: float = Field(default=1.0, ge=0.0, le=1.0)


class UnderwritingReport(BaseModel):
    """Consolidated due diligence verdict synthesized by swarm."""

    parcel_id: str
    status: UnderwritingStatus = UnderwritingStatus.PENDING
    overall_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    findings: List[UnderwritingFinding] = Field(default_factory=list)
    summary: str = ""


# =====================================================================
# MCP Server Tool Models
# =====================================================================


class MCPToolCall(BaseModel):
    """Structured tool execution invocation."""

    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPToolResult(BaseModel):
    """Result returned by MCP tool execution."""

    tool: str
    content: Any
    is_error: bool = False
