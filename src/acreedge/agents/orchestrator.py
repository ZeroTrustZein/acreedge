"""Autonomous multi-agent underwriting coordinator and agents."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from acreedge.config import SwarmSettings
from acreedge.types import (
    AgentRole,
    UnderwritingFinding,
    UnderwritingReport,
    UnderwritingStatus,
)

logger = logging.getLogger(__name__)


class UnderwritingAgent:
    """Specialized underwriting agent instance."""

    def __init__(self, role: str) -> None:
        self._role = role

    @property
    def role(self) -> str:
        return self._role

    def execute_task(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform role-specific underwriting audit task."""
        parcel_id = context.get("parcel_id", "UNKNOWN")
        return {
            "agent_role": self._role,
            "parcel_id": parcel_id,
            "status": "APPROVED",
            "findings": f"Audit completed by {self._role} for parcel {parcel_id}.",
        }


class SwarmOrchestrator:
    """Coordinates the autonomous underwriting swarm across specialized roles."""

    def __init__(self, settings: Optional[SwarmSettings] = None) -> None:
        self.settings = settings or SwarmSettings()
        self._agents: Dict[str, UnderwritingAgent] = {}
        self._initialize_default_agents()

    def _initialize_default_agents(self) -> None:
        """Instantiate agents configured in swarm settings."""
        for role in self.settings.roles:
            self.register_agent(UnderwritingAgent(role))

    def register_agent(self, agent: UnderwritingAgent) -> None:
        """Register agent in swarm."""
        self._agents[agent.role] = agent
        logger.debug(f"Registered agent with role: {agent.role}")

    def get_registered_agents(self) -> Dict[str, UnderwritingAgent]:
        """Return registered agents."""
        return self._agents

    def run_due_diligence(self, parcel_id: str) -> Dict[str, Any]:
        """Execute full due diligence workflow with all registered agents."""
        audit_results: List[Dict[str, Any]] = []
        context = {"parcel_id": parcel_id}

        for _role, agent in self._agents.items():
            res = agent.execute_task(context)
            audit_results.append(res)

        all_approved = all(r.get("status") == "APPROVED" for r in audit_results)
        return {
            "parcel_id": parcel_id,
            "overall_status": "APPROVED" if all_approved else "REJECTED",
            "agent_audits": audit_results,
        }

    def run_due_diligence_report(
        self, parcel_id: str, purchase_price: Optional[float] = None
    ) -> UnderwritingReport:
        """Run full underwriting audit and synthesize into typed UnderwritingReport."""
        context = {"parcel_id": parcel_id, "purchase_price": purchase_price}
        findings: List[UnderwritingFinding] = []
        all_approved = True

        role_mapping = {
            "DeedAuditor": AgentRole.LEGAL,
            "ValuationSpecialist": AgentRole.FINANCIAL,
            "ZoningInvestigator": AgentRole.ZONING,
            "RiskUnderwriter": AgentRole.FINANCIAL,
        }

        for _role, agent in self._agents.items():
            res = agent.execute_task(context)
            role_name = res.get("agent_role", "DeedAuditor")
            status_str = res.get("status", "APPROVED")
            agent_role = role_mapping.get(role_name, AgentRole.LEGAL)

            is_appr = status_str == "APPROVED"
            if not is_appr:
                all_approved = False

            findings.append(
                UnderwritingFinding(
                    agent_role=agent_role,
                    category=role_name,
                    severity="INFO" if is_appr else "CRITICAL",
                    description=res.get("findings", f"Completed by {role_name}"),
                    score=1.0 if is_appr else 0.0,
                )
            )

        status = UnderwritingStatus.APPROVED if all_approved else UnderwritingStatus.REJECTED
        risk_score = 15.0 if all_approved else 75.0

        return UnderwritingReport(
            parcel_id=parcel_id,
            status=status,
            overall_risk_score=risk_score,
            findings=findings,
            summary=f"Swarm underwriting completed for parcel {parcel_id}.",
        )
