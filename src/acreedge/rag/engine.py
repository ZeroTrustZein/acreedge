"""Hybrid pgvector and Graph-RAG retrieval engine for real estate due diligence."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from acreedge.config import RAGSettings
from acreedge.types import RAGSearchResult

logger = logging.getLogger(__name__)


class HybridRAGEngine:
    """Combines dense vector retrieval (pgvector) with knowledge-graph deed relationships."""

    def __init__(self, settings: Optional[RAGSettings] = None) -> None:
        self.settings = settings or RAGSettings()
        self._doc_index: Dict[str, Dict[str, Any]] = {}
        self._graph_edges: List[Dict[str, Any]] = []

    def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """Store document with metadata and simulated embedding vector."""
        self._doc_index[doc_id] = {
            "content": content,
            "metadata": metadata,
            "vector_dim": self.settings.vector_dim,
        }
        return True

    def add_graph_relation(self, source_entity: str, relation: str, target_entity: str) -> None:
        """Add knowledge graph edge between real estate entities (e.g. Parcel -> Grantor)."""
        self._graph_edges.append({
            "source": source_entity,
            "relation": relation,
            "target": target_entity,
        })

    def hybrid_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Simulate hybrid retrieval combining dense score and graph connectivity."""
        k = top_k or self.settings.top_k
        results: List[Dict[str, Any]] = []

        # Find matching entities or documents
        for doc_id, doc in list(self._doc_index.items())[:k]:
            results.append({
                "doc_id": doc_id,
                "content": doc["content"],
                "score": 0.88,
                "graph_neighbors": [
                    edge["target"] for edge in self._graph_edges if edge["source"] == doc_id
                ],
            })
        return results

    def get_chain_of_title(self, parcel_id: str) -> List[Dict[str, Any]]:
        """Retrieve historical ownership and conveyance edges for a parcel."""
        return [
            edge
            for edge in self._graph_edges
            if edge["source"] == parcel_id or edge["target"] == parcel_id
        ]

    def search_models(self, query: str, top_k: Optional[int] = None) -> List[RAGSearchResult]:
        """Hybrid search returning typed RAGSearchResult schemas."""
        hits = self.hybrid_search(query, top_k)
        return [
            RAGSearchResult(
                doc_id=h["doc_id"],
                content=h["content"],
                score=h["score"],
                graph_relevance=0.85 if h.get("graph_neighbors") else 0.0,
                metadata={"graph_neighbors": h.get("graph_neighbors", [])},
            )
            for h in hits
        ]
