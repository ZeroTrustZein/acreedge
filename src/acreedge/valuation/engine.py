"""Valuation engine implementing direct capitalization and DCF metrics."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

from acreedge.types import CleanDeedRecord, DCFAnalysis, ValuationInput, ValuationResult

logger = logging.getLogger(__name__)


class ValuationEngine:
    """Core real estate valuation model engine."""

    def calculate_cap_rate(self, noi: float, property_value: float) -> float:
        """Calculate capitalization rate: NOI / Property Value."""
        if property_value <= 0:
            raise ValueError("Property value must be greater than zero")
        return round(noi / property_value, 4)

    def calculate_comps_valuation(
        self,
        comps: List[Union[Dict[str, Any], CleanDeedRecord]],
        target_sqft: float = 1.0,
    ) -> Dict[str, Any]:
        """Estimate valuation based on sales comparables."""
        if not comps:
            return {"estimated_value": 0.0, "comp_count": 0, "avg_price": 0.0}

        prices: List[float] = []
        for comp in comps:
            if isinstance(comp, CleanDeedRecord):
                prices.append(float(comp.sale_price))
            elif isinstance(comp, dict):
                prices.append(float(comp.get("sale_price", 0.0)))

        valid_prices = [p for p in prices if p > 0]
        if not valid_prices:
            return {"estimated_value": 0.0, "comp_count": 0, "avg_price": 0.0}

        avg_price = sum(valid_prices) / len(valid_prices)
        return {
            "estimated_value": round(avg_price, 2),
            "comp_count": len(valid_prices),
            "avg_price": round(avg_price, 2),
        }

    def calculate_valuation(
        self, property_data: Union[Dict[str, Any], ValuationInput]
    ) -> Dict[str, Any]:
        """Estimate property valuation via direct capitalization and comps."""
        data = (
            property_data.model_dump()
            if isinstance(property_data, ValuationInput)
            else property_data
        )
        noi = float(data.get("noi", 0.0))
        target_cap_rate = float(data.get("cap_rate", 0.065))
        square_feet = float(data.get("square_feet", 1.0))
        parcel_id = str(data.get("parcel_id", "UNKNOWN"))
        comps = data.get("comps", [])

        if target_cap_rate <= 0:
            target_cap_rate = 0.065

        if noi > 0:
            estimated_value = noi / target_cap_rate
        elif comps:
            comps_res = self.calculate_comps_valuation(comps, square_feet)
            estimated_value = comps_res["estimated_value"]
        else:
            estimated_value = 0.0

        val_per_sqft = estimated_value / square_feet if square_feet > 0 else 0.0

        return {
            "parcel_id": parcel_id,
            "estimated_value": round(estimated_value, 2),
            "noi": round(noi, 2),
            "cap_rate": round(target_cap_rate, 4),
            "value_per_sqft": round(val_per_sqft, 2),
            "confidence_score": 0.92,
        }

    def evaluate(self, inp: ValuationInput) -> ValuationResult:
        """Strongly-typed valuation model evaluation."""
        raw = self.calculate_valuation(inp)
        return ValuationResult(**raw)

    def calculate_dcf(
        self, cash_flows: List[float], discount_rate: float, terminal_value: float = 0.0
    ) -> float:
        """Calculate Discounted Cash Flow Net Present Value (NPV)."""
        if discount_rate <= -1.0:
            raise ValueError("Discount rate cannot be <= -100%")

        npv = 0.0
        for year, cf in enumerate(cash_flows, start=1):
            npv += cf / ((1.0 + discount_rate) ** year)

        if terminal_value > 0 and len(cash_flows) > 0:
            npv += terminal_value / ((1.0 + discount_rate) ** len(cash_flows))

        return round(npv, 2)

    def evaluate_dcf(
        self, cash_flows: List[float], discount_rate: float, terminal_value: float = 0.0
    ) -> DCFAnalysis:
        """Calculate Discounted Cash Flow and return DCFAnalysis schema."""
        npv = self.calculate_dcf(cash_flows, discount_rate, terminal_value)
        return DCFAnalysis(
            cash_flows=cash_flows,
            discount_rate=discount_rate,
            terminal_value=terminal_value,
            npv=npv,
        )
