"""Structural subtyping protocols defining core AcreEdge contracts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class DatabaseManagerProtocol(Protocol):
    """Protocol for PostgreSQL and pgvector database manager."""

    def initialize_schema(self) -> bool: ...
    def execute_query(
        self, sql: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]: ...
    def is_connected(self) -> bool: ...


@runtime_checkable
class RawExportValidatorProtocol(Protocol):
    """Protocol for SQL-based cleaning and validation of raw municipal exports."""

    def generate_validation_sql(self) -> str: ...
    def validate_batch(self, records: List[Dict[str, Any]]) -> Dict[str, Any]: ...
    def clean_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...


@runtime_checkable
class MunicipalDeedIngestionProtocol(Protocol):
    """Protocol for municipal deed ingestion pipelines."""

    def ingest_raw_export(self, source_path: str) -> Dict[str, Any]: ...
    def run_cleaning_pipeline(self) -> Dict[str, Any]: ...


@runtime_checkable
class ValuationModelProtocol(Protocol):
    """Protocol for real estate valuation models."""

    def calculate_valuation(self, property_data: Dict[str, Any]) -> Dict[str, Any]: ...
    def calculate_cap_rate(self, noi: float, property_value: float) -> float: ...


@runtime_checkable
class MCPServerProtocol(Protocol):
    """Protocol for custom AcreEdge MCP server."""

    def register_tool(self, name: str, handler: Any) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


@runtime_checkable
class HybridRAGProtocol(Protocol):
    """Protocol for pgvector and Graph-RAG retrieval."""

    def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any]) -> bool: ...
    def hybrid_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]: ...


@runtime_checkable
class SwarmAgentProtocol(Protocol):
    """Protocol for specialized underwriting swarm agents."""

    @property
    def role(self) -> str: ...
    def execute_task(self, context: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class SwarmOrchestratorProtocol(Protocol):
    """Protocol for the autonomous underwriting swarm coordinator."""

    def register_agent(self, agent: SwarmAgentProtocol) -> None: ...
    def run_due_diligence(self, parcel_id: str) -> Dict[str, Any]: ...
