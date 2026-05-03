"""
Unified Pricing Engine — Single source of truth for all pricing logic.

Handles:
- Bulk/tier-based pricing computation
- Negotiation request evaluation (auto-accept, risk assessment)
- AI demand-aware pricing adjustments
- Savings suggestions for upsell

IMPORTANT: All pricing decisions MUST go through this service.
"""

import logging
from typing import Optional, List
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from models.core import Product, PricingTier, ProductInsight

logger = logging.getLogger(__name__)


# ======================== DECIMAL SAFETY (FIX 5) ========================

def normalize_price(value) -> float:
    """Round to 2 decimal places using banker's rounding."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ======================== RESPONSE TYPES ========================

@dataclass
class PricingResult:
    base_price: float
    bulk_price: float
    best_price: float
    savings: float
    tier_applied: bool
    tier_min_qty: Optional[int] = None
    suggestion: Optional[str] = None
    ai_suggestion: Optional[str] = None
    aggressive_negotiation_allowed: bool = True


@dataclass
class NegotiationEvaluation:
    auto_accept: bool
    risk_level: str       # "safe" | "negotiable" | "lowball"
    bulk_price: float
    margin_percent: float
    reason: str


@dataclass
class AIContext:
    demand_score: float = 0.0         # 0-1 normalized
    stockout_risk: str = "none"       # none, low, medium, high, critical
    is_dead_stock: bool = False
    priority_score: float = 0.0


# ======================== PRICING ENGINE ========================

class PricingEngine:
    """Stateless pricing engine. Thread-safe, no internal state."""

    @staticmethod
    def get_tiers(db: Session, product_id: int, shop_id: int) -> List[PricingTier]:
        return (
            db.query(PricingTier)
            .filter(PricingTier.product_id == product_id, PricingTier.shop_id == shop_id)
            .order_by(PricingTier.min_qty.asc())
            .all()
        )

    @staticmethod
    def get_bulk_price(db: Session, product: Product, quantity: int) -> tuple:
        """Returns (price_per_unit, tier_applied, tier_min_qty)."""
        tiers = PricingEngine.get_tiers(db, product.id, product.shop_id)
        best_tier = None
        for tier in tiers:
            if tier.min_qty <= quantity:
                best_tier = tier
        if best_tier:
            return (normalize_price(best_tier.price_per_unit), True, best_tier.min_qty)
        return (normalize_price(product.selling_price or 0.0), False, None)

    # ===================== AI CONTEXT (PART 3) =====================

    @staticmethod
    def get_ai_context(db: Session, product: Product) -> AIContext:
        """
        Fetch AI demand signals from product_insights table.
        FIX 4: If data is stale (>24h), fall back to default — no AI influence.
        """
        from datetime import datetime, timedelta

        insight = (
            db.query(ProductInsight)
            .filter(ProductInsight.product_id == product.id)
            .first()
        )
        if not insight:
            return AIContext()

        # Staleness protection: ignore AI data older than 24 hours
        if insight.updated_at and insight.updated_at < datetime.utcnow() - timedelta(hours=24):
            logger.info("[AI_STALE] product=%d insight_updated=%s — falling back to default pricing", product.id, insight.updated_at)
            return AIContext()

        raw_demand = insight.predicted_daily_demand or 0.0
        demand_score = min(raw_demand / 100.0, 1.0)

        return AIContext(
            demand_score=round(demand_score, 3),
            stockout_risk=insight.stockout_risk or "none",
            is_dead_stock=insight.is_dead_stock or False,
            priority_score=insight.priority_score or 0.0,
        )

    @staticmethod
    def _ai_suggestion_text(ai: AIContext) -> Optional[str]:
        """Generate human-readable AI pricing suggestion."""
        if ai.demand_score > 0.8:
            return "High demand — price is firm, limited negotiation"
        if ai.stockout_risk in ("high", "critical"):
            return "Low stock risk — price unlikely to be reduced"
        if ai.is_dead_stock:
            return "Slow-moving item — open to aggressive offers"
        if ai.demand_score < 0.2:
            return "Low demand — flexible pricing available"
        return None

    # ===================== SMART PRICING =====================

    @staticmethod
    def get_smart_price(db: Session, product: Product, quantity: int) -> PricingResult:
        base_price = normalize_price(product.selling_price or 0.0)
        bulk_ppu, tier_applied, tier_min_qty = PricingEngine.get_bulk_price(db, product, quantity)
        best_price = bulk_ppu
        total_savings = normalize_price((base_price - best_price) * quantity) if tier_applied else 0.0

        # Upsell suggestion
        suggestion = None
        tiers = PricingEngine.get_tiers(db, product.id, product.shop_id)
        for tier in tiers:
            if tier.min_qty > quantity:
                extra_savings = normalize_price((base_price - tier.price_per_unit) * tier.min_qty)
                suggestion = f"Buy {tier.min_qty}+ to save ₹{extra_savings:.0f} total"
                break

        # AI context
        ai = PricingEngine.get_ai_context(db, product)
        aggressive_allowed = ai.demand_score < 0.7 and ai.stockout_risk not in ("high", "critical")

        return PricingResult(
            base_price=base_price,
            bulk_price=bulk_ppu,
            best_price=best_price,
            savings=max(total_savings, 0.0),
            tier_applied=tier_applied,
            tier_min_qty=tier_min_qty,
            suggestion=suggestion,
            ai_suggestion=PricingEngine._ai_suggestion_text(ai),
            aggressive_negotiation_allowed=aggressive_allowed,
        )

    # ===================== NEGOTIATION EVALUATION =====================

    @staticmethod
    def evaluate_request(
        db: Session, product: Product, quantity: int, requested_price: float,
    ) -> NegotiationEvaluation:
        """
        AI-enhanced negotiation evaluation.
        High demand → stricter thresholds. Low demand → more lenient.
        """
        requested_price = normalize_price(requested_price)
        bulk_ppu, _, _ = PricingEngine.get_bulk_price(db, product, quantity)

        cost_price = normalize_price(product.cost_price or 0.0)
        if cost_price > 0 and requested_price <= cost_price:
            logger.info("[NEGOTIATION_EVAL] REJECT below cost: product=%d price=%.2f cost=%.2f", product.id, requested_price, cost_price)
            return NegotiationEvaluation(
                auto_accept=False, risk_level="lowball", bulk_price=bulk_ppu,
                margin_percent=-100.0,
                reason=f"Requested ₹{requested_price:.2f} is at or below cost (₹{cost_price:.2f})",
            )

        if bulk_ppu <= 0:
            return NegotiationEvaluation(
                auto_accept=False, risk_level="negotiable", bulk_price=0.0,
                margin_percent=0.0, reason="No base price configured",
            )

        # AI-adjusted thresholds
        ai = PricingEngine.get_ai_context(db, product)
        if ai.demand_score > 0.8:
            auto_accept_threshold = bulk_ppu * 0.98   # Only 2% discount for hot items
            negotiable_threshold = bulk_ppu * 0.95
        elif ai.demand_score < 0.2 or ai.is_dead_stock:
            auto_accept_threshold = bulk_ppu * 0.90   # 10% off for slow movers
            negotiable_threshold = bulk_ppu * 0.80
        else:
            auto_accept_threshold = bulk_ppu           # Default: exact match
            negotiable_threshold = bulk_ppu * 0.90

        margin = ((bulk_ppu - requested_price) / bulk_ppu) * 100

        if requested_price >= auto_accept_threshold:
            return NegotiationEvaluation(
                auto_accept=True, risk_level="safe", bulk_price=bulk_ppu,
                margin_percent=round(margin, 1),
                reason="Price meets threshold — auto-acceptable",
            )
        if requested_price >= negotiable_threshold:
            return NegotiationEvaluation(
                auto_accept=False, risk_level="negotiable", bulk_price=bulk_ppu,
                margin_percent=round(margin, 1),
                reason=f"Price is {margin:.1f}% below bulk — within negotiation range",
            )
        return NegotiationEvaluation(
            auto_accept=False, risk_level="lowball", bulk_price=bulk_ppu,
            margin_percent=round(margin, 1),
            reason=f"Price is {margin:.1f}% below bulk — flagged as lowball",
        )
