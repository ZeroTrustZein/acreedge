"""AcreEdge global settings and configuration definitions."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """PostgreSQL connection and pooling configuration."""

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    user: str = Field(default="postgres", description="PostgreSQL user")
    password: str = Field(default="postgres", description="PostgreSQL password")
    name: str = Field(default="acreedge_db", description="Database name")
    sslmode: str = Field(default="prefer", description="SSL connection mode")
    pool_size: int = Field(default=10, description="Connection pool size")

    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class MCPSettings(BaseModel):
    """Model Context Protocol (MCP) server configuration."""

    host: str = Field(default="127.0.0.1", description="Server bind host")
    port: int = Field(default=8440, description="Server port")
    endpoint_path: str = Field(default="/mcp/v1", description="MCP base route")
    timeout_seconds: float = Field(default=30.0, description="Request timeout")


class RAGSettings(BaseModel):
    """Hybrid pgvector and Graph-RAG settings."""

    vector_dim: int = Field(default=1536, description="Embedding vector dimensions")
    embedding_model: str = Field(default="text-embedding-3-small", description="Default model name")
    top_k: int = Field(default=5, description="Number of results to retrieve")
    similarity_threshold: float = Field(default=0.75, description="Minimum cosine score")
    hybrid_alpha: float = Field(default=0.6, description="Weight for dense vs graph rank")


class IngestionSettings(BaseModel):
    """Municipal deed ingestion and raw export validation settings."""

    raw_export_table: str = Field(default="raw_municipal_deeds", description="Staging table name")
    clean_table: str = Field(default="validated_deeds", description="Validated table name")
    batch_size: int = Field(default=1000, description="Batch insert size")
    min_sale_price: float = Field(default=100.0, description="Threshold for valid deed transfers")
    require_parcel_id: bool = Field(default=True, description="Enforce parcel identifier")


class SwarmSettings(BaseModel):
    """Autonomous underwriting swarm configuration."""

    max_concurrent_agents: int = Field(default=4, description="Max parallel agents")
    roles: List[str] = Field(
        default_factory=lambda: [
            "DeedAuditor",
            "ValuationSpecialist",
            "ZoningInvestigator",
            "RiskUnderwriter",
        ],
        description="Active agent personas",
    )


class AcreEdgeSettings(BaseSettings):
    """Root configuration for AcreEdge."""

    model_config = SettingsConfigDict(
        env_prefix="ACREEDGE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    project_name: str = "AcreEdge"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    swarm: SwarmSettings = Field(default_factory=SwarmSettings)
