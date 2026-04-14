import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
# We use TTLCache to avoid Redis dependency for the MVP while still honoring TTL parameters
from cachetools import TTLCache

from models.core import Product, Inventory, Sale
from schemas.core import PredictionResponse
from logic_engine import DataSanitizer, DemandPredictor, InventoryLogic

logger = logging.getLogger(__name__)

# Global singleton cache. Max 10,000 predictions, 600 seconds (10 min) TTL.
prediction_cache = TTLCache(maxsize=10000, ttl=600)

def invalidate_prediction_cache(shop_id: int, product_id: int):
    """
    Triggered immediately when a new sale occurs. 
    Evicts the mathematically compromised ML cache across varying window sizes.
    """
    # In python TTLCache, we pop known possible windows (e.g. 7, 14, 30).
    # In production Redis setups, you would use wildcard deletes: DEL "shop:product:*"
    for window in [7, 14, 30, 90]:
        cache_key = f"{shop_id}:{product_id}:{window}"
        popped = prediction_cache.pop(cache_key, None)
        if popped:
            logger.info(f"CACHE INVALIDATED - Stale logic cleared for key: {cache_key}")

def get_product_prediction(db: Session, shop_id: int, product_id: int, window_size: int = 14):
    """Read-only prediction logic pipeline wrapped in high-speed memoization."""
    # 1. Enforce specific Multi-tenant Isolation Cache Key
    cache_key = f"{shop_id}:{product_id}:{window_size}"
    
    if cache_key in prediction_cache:
        logger.info(f"CACHE HIT -> Rapid serving memoized logic for: {cache_key}")
        return prediction_cache[cache_key]
        
    logger.info(f"CACHE MISS -> Calculating expensive ML logic for: {cache_key}")
    
    product = db.query(Product).filter(Product.id == product_id, Product.shop_id == shop_id).first()
    inventory = db.query(Inventory).filter(Inventory.product_id == product_id, Inventory.shop_id == shop_id).first()
    
    if not product or not inventory:
        logger.error(f"Prediction aborted: Item not found (Shop {shop_id}, Product {product_id})")
        raise ValueError("Product or Inventory not found.")

    cutoff = datetime.utcnow() - timedelta(days=14)
    sales = db.query(Sale).filter(
        Sale.shop_id == shop_id,
        Sale.product_id == product_id,
        Sale.sale_date >= cutoff
    ).order_by(Sale.sale_date.asc()).all()
    
    if not sales:
        result = {
            "prediction": "No data",
            "estimated_daily_sales": 0.0,
            "target_safety_buffer": 0,
            "reorder_now": False
        }
        prediction_cache[cache_key] = result
        return result

    total_sold = sum(s.quantity_sold for s in sales)

    window_days = 14
    avg_daily_sales = total_sold / window_days

    trend_factor = 1.2 if total_sold > 10 else 1
    forecast = avg_daily_sales * trend_factor

    safety_stock = forecast * 2

    result = {
        "prediction": "Increase stock" if forecast > 0 else "Stable",
        "estimated_daily_sales": round(forecast, 2),
        "target_safety_buffer": int(safety_stock),
        "reorder_now": inventory.quantity_on_hand < safety_stock
    }
    
    prediction_cache[cache_key] = result
    return result
