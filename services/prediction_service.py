import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
# We use TTLCache to avoid Redis dependency for the MVP while still honoring TTL parameters
from cachetools import TTLCache

from models.core import Product, Inventory, SaleTransaction
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

def get_product_prediction(db: Session, shop_id: int, product_id: int, window_size: int = 14) -> PredictionResponse:
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

    lookback_date = datetime.utcnow() - timedelta(days=window_size)
    sales = db.query(SaleTransaction).filter(
        SaleTransaction.shop_id == shop_id,
        SaleTransaction.product_id == product_id,
        SaleTransaction.sale_date >= lookback_date
    ).order_by(SaleTransaction.sale_date.asc()).all()
    
    raw_sales_array = [s.quantity_sold for s in sales] 
    cleaned_sales = DataSanitizer.validate_and_clean(raw_sales_array)
    
    if not cleaned_sales or len(cleaned_sales) < (window_size // 3):
        return PredictionResponse(
            product_id=product.id,
            suggested_order_qty=product.lead_time_days * 2.0, 
            predicted_daily_demand=0.0,
            safety_stock_required=0.0,
            reorder_point=0.0,
            current_inventory=inventory.quantity_on_hand,
            action_required="Sparse Data. Default Fallback."
        )

    window_length = len(cleaned_sales)
    dynamic_weights = [(1.0/window_length)] * window_length
    
    wma = DemandPredictor.adaptive_weighted_moving_average(cleaned_sales, base_weights=dynamic_weights)
    
    safety_stock = InventoryLogic.calculate_safety_stock(
        sales_data=cleaned_sales,
        avg_lead_time_days=product.lead_time_days
    )
    
    reorder_point = InventoryLogic.calculate_reorder_point(
        predicted_daily_demand=wma,
        lead_time_days=product.lead_time_days,
        safety_stock=safety_stock
    )
    
    order_qty = InventoryLogic.suggest_order_quantity(
        current_inventory=inventory.quantity_on_hand,
        reorder_point=reorder_point,
        predicted_daily_demand=wma,
        lead_time_days=product.lead_time_days
    )
    
    response = PredictionResponse(
        product_id=product.id,
        suggested_order_qty=order_qty,
        predicted_daily_demand=wma,
        safety_stock_required=safety_stock,
        reorder_point=reorder_point,
        current_inventory=inventory.quantity_on_hand,
        action_required=f"Order {order_qty:.0f} units" if order_qty > 0 else "Stock healthy."
    )
    
    # 2. Store calculation in cache before returning
    prediction_cache[cache_key] = response
    return response
