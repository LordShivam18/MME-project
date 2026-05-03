"""
Unified Pricing Engine — Single source of truth for all pricing logic.

Handles:
- Bulk/tier-based pricing computation
- Negotiation request evaluation (auto-accept, risk assessment)
- Savings suggestions for upsell

IMPORTANT: All pricing decisions MUST go through this service.
Do NOT compute prices in controllers/routers directly.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.core import Product, PricingTier, PriceRequest

logger = logging.getLogger(__name__)


# ======================== RESPONSE TYPES ========================

@dataclass
class PricingResult:
    """Returned by get_smart_price() — full pricing breakdown."""
    base_price: float           # product.selling_price
    bulk_price: float           # tier price (or base if no tier)
    best_price: float           # lowest available price
    savings: float              # base_price - best_price (total, not per-unit)
    tier_applied: bool          # whether a tier was matched
    tier_min_qty: Optional[int] # the tier's min_qty (if applied)
    suggestion: Optional[str]   # upsell suggestion text


@dataclass
class NegotiationEvaluation:
    """Returned by evaluate_request() — risk assessment."""
    auto_accept: bool
    risk_level: str             # "safe" | "negotiable" | "lowball"
    bulk_price: float           # reference price used for comparison
    margin_percent: float       # how far below bulk_price the request is
    reason: str                 # human-readable explanation


# ======================== PRICING ENGINE ========================

class PricingEngine:
    """
    Stateless pricing engine. All methods take DB session + data as params.
    Thread-safe, no internal state.
    """

    @staticmethod
    def get_tiers(db: Session, product_id: int, shop_id: int) -> List[PricingTier]:
        """Fetch all pricing tiers for a product, ordered by min_qty ASC."""
        return (
            db.query(PricingTier)
            .filter(
                PricingTier.product_id == product_id,
                PricingTier.shop_id == shop_id,
            )
            .order_by(PricingTier.min_qty.asc())
            .all()
        )

    @staticmethod
    def get_bulk_price(db: Session, product: Product, quantity: int) -> tuple:
        """
        Returns (price_per_unit, tier_applied, tier_min_qty).
        Finds the highest tier where min_qty <= quantity.
        Falls back to product.selling_price if no tier matches.
        """
        tiers = PricingEngine.get_tiers(db, product.id, product.shop_id)

        best_tier = None
        for tier in tiers:
            if tier.min_qty <= quantity:
                best_tier = tier  # keep overwriting — tiers are ASC, so last match is highest

        if best_tier:
            return (best_tier.price_per_unit, True, best_tier.min_qty)

        return (product.selling_price or 0.0, False, None)

    @staticmethod
    def get_smart_price(db: Session, product: Product, quantity: int) -> PricingResult:
        """
        Full pricing computation with savings calculation and upsell suggestion.
        """
        base_price = product.selling_price or 0.0
        bulk_price_per_unit, tier_applied, tier_min_qty = PricingEngine.get_bulk_price(db, product, quantity)

        best_price = bulk_price_per_unit
        total_savings = round((base_price - best_price) * quantity, 2) if tier_applied else 0.0

        # Generate upsell suggestion: find the next tier above current quantity
        suggestion = None
        tiers = PricingEngine.get_tiers(db, product.id, product.shop_id)
        for tier in tiers:
            if tier.min_qty > quantity:
                extra_savings = round((base_price - tier.price_per_unit) * tier.min_qty, 2)
                suggestion = f"Buy {tier.min_qty}+ to save ₹{extra_savings:.0f} total"
                break

        return PricingResult(
            base_price=round(base_price, 2),
            bulk_price=round(bulk_price_per_unit, 2),
            best_price=round(best_price, 2),
            savings=max(total_savings, 0.0),
            tier_applied=tier_applied,
            tier_min_qty=tier_min_qty,
            suggestion=suggestion,
        )

    @staticmethod
    def evaluate_request(
        db: Session,
        product: Product,
        quantity: int,
        requested_price: float,
    ) -> NegotiationEvaluation:
        """
        Evaluate a price negotiation request against bulk pricing.

        Decision matrix:
        - requested >= bulk_price        → auto_accept, "safe"
        - requested >= bulk_price * 0.90 → manual review, "negotiable"
        - requested <  bulk_price * 0.90 → flag, "lowball"
        - requested <= cost_price        → reject outright
        """
        bulk_price_per_unit, _, _ = PricingEngine.get_bulk_price(db, product, quantity)

        # Safety: prevent under-cost pricing
        cost_price = product.cost_price or 0.0
        if cost_price > 0 and requested_price <= cost_price:
            return NegotiationEvaluation(
                auto_accept=False,
                risk_level="lowball",
                bulk_price=round(bulk_price_per_unit, 2),
                margin_percent=-100.0,
                reason=f"Requested price ₹{requested_price:.2f} is at or below cost (₹{cost_price:.2f})",
            )

        # Compare against bulk price
        if bulk_price_per_unit <= 0:
            return NegotiationEvaluation(
                auto_accept=False,
                risk_level="negotiable",
                bulk_price=0.0,
                margin_percent=0.0,
                reason="No base price configured",
            )

        margin = ((bulk_price_per_unit - requested_price) / bulk_price_per_unit) * 100

        if requested_price >= bulk_price_per_unit:
            return NegotiationEvaluation(
                auto_accept=True,
                risk_level="safe",
                bulk_price=round(bulk_price_per_unit, 2),
                margin_percent=round(margin, 1),
                reason="Price meets or exceeds bulk rate — auto-acceptable",
            )

        if requested_price >= bulk_price_per_unit * 0.90:
            return NegotiationEvaluation(
                auto_accept=False,
                risk_level="negotiable",
                bulk_price=round(bulk_price_per_unit, 2),
                margin_percent=round(margin, 1),
                reason=f"Price is {margin:.1f}% below bulk rate — within negotiation range",
            )

        return NegotiationEvaluation(
            auto_accept=False,
            risk_level="lowball",
            bulk_price=round(bulk_price_per_unit, 2),
            margin_percent=round(margin, 1),
            reason=f"Price is {margin:.1f}% below bulk rate — flagged as lowball",
        )
