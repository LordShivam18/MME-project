import logging
from sqlalchemy.orm import Session
from models.core import Product, Inventory, Sale, ProductInsight
from schemas.core import PredictionResponse

logger = logging.getLogger(__name__)

def invalidate_prediction_cache(shop_id: int, product_id: int):
    # No longer needed - predictions are pre-computed daily via cron.
    pass

def get_product_prediction(db: Session, shop_id: int, product_id: int, window_size: int = 14):
    """Returns pre-computed AI insights from DB, achieving O(1) latency."""
    logger.info(f"Fetching precomputed AI insight for product_id: {product_id}")
    
    insight_record = db.query(ProductInsight).filter(
        ProductInsight.product_id == product_id,
        ProductInsight.organization_id == shop_id
    ).first()
    
    if insight_record:
        return {
            "product_id": insight_record.product_id,
            "insight": insight_record.insight,
            "recommended_action": insight_record.recommended_action,
            "confidence_score": insight_record.confidence_score,
            "predicted_daily_demand": insight_record.predicted_daily_demand
        }
    
    # Fallback if cron hasn't run yet
    return {
        "product_id": product_id,
        "insight": "Analyzing Data",
        "recommended_action": "Check back tomorrow for AI insights after nightly job.",
        "confidence_score": 0,
        "predicted_daily_demand": 0.0
    }
