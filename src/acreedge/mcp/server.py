"""Custom MCP server exposing valuation models and municipal deed pipelines."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from acreedge.config import MCPSettings
from acreedge.types import MCPToolCall, MCPToolResult

logger = logging.getLogger(__name__)


class AcreEdgeMCPServer:
    """Custom MCP Server exposing real estate valuation and deed due diligence tools."""

    def __init__(self, settings: Optional[MCPSettings] = None) -> None:
        self.settings = settings or MCPSettings()
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._running: bool = False
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default valuation and municipal deed tools."""
        self.register_tool("calculate_valuation", self._tool_calculate_valuation)
        self.register_tool("query_validated_deeds", self._tool_query_deeds)
        self.register_tool("underwrite_property", self._tool_underwrite_property)

    def register_tool(self, name: str, handler: Callable[..., Any]) -> None:
        """Register an MCP tool endpoint."""
        self._tools[name] = handler
        logger.debug(f"Registered MCP tool: {name}")

    def get_registered_tools(self) -> Dict[str, Callable[..., Any]]:
        """Return registered tools dictionary."""
        return self._tools

    def start(self) -> None:
        """Start the MCP server."""
        self._running = True
        logger.info(f"AcreEdge MCP server started on {self.settings.host}:{self.settings.port}")

    def stop(self) -> None:
        """Stop the MCP server."""
        self._running = False
        logger.info("AcreEdge MCP server stopped")

    def is_running(self) -> bool:
        """Return server run state."""
        return self._running

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a registered tool by name with arguments."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        handler = self._tools[name]
        return handler(**arguments)

    def call_tool(self, call: MCPToolCall) -> MCPToolResult:
        """Process structured MCPToolCall and return strongly-typed MCPToolResult."""
        try:
            result = self.execute_tool(call.name, call.arguments)
            return MCPToolResult(tool=call.name, content=result, is_error=False)
        except Exception as exc:
            return MCPToolResult(
                tool=call.name,
                content=str(exc),
                is_error=True,
            )

    def _tool_calculate_valuation(self, noi: float, cap_rate: float) -> Dict[str, Any]:
        """Tool implementation for direct capitalization valuation."""
        if cap_rate <= 0:
            raise ValueError("Cap rate must be greater than zero")
        val = noi / cap_rate
        return {"estimated_value": round(val, 2), "noi": noi, "cap_rate": cap_rate}

    def _tool_query_deeds(self, parcel_id: str) -> Dict[str, Any]:
        """Tool implementation for deed lookups."""
        return {"parcel_id": parcel_id, "deeds_found": 0, "records": []}

    def _tool_underwrite_property(self, parcel_id: str, purchase_price: float) -> Dict[str, Any]:
        """Tool implementation for initial deal underwriting."""
        return {
            "parcel_id": parcel_id,
            "purchase_price": purchase_price,
            "status": "initial_review",
            "decision": "PENDING_AUDIT",
        }
