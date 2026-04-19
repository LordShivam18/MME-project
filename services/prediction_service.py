import logging
from sqlalchemy.orm import Session
from models.core import Product, Inventory, Sale, ProductInsight, Contact, Order, OrderItem
from schemas.core import PredictionResponse
from sqlalchemy import func

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
        # Determine CRM supplier linking
        supplier_id = None
        supplier_name = None
        
        # 1. Most Frequent Supplier for this exact product
        freq_supplier = db.query(Contact.id, Contact.name, func.count(Order.id).label('ord_count')).\
            join(Order, Order.contact_id == Contact.id).\
            join(OrderItem, OrderItem.order_id == Order.id).\
            filter(OrderItem.product_id == product_id, Contact.organization_id == shop_id, Contact.type == 'supplier').\
            group_by(Contact.id, Contact.name).\
            order_by(func.count(Order.id).desc()).first()
            
        if freq_supplier:
            supplier_id, supplier_name, _ = freq_supplier
        else:
            # 2. Fallback to Any general Supplier in CRM
            any_supplier = db.query(Contact).filter(
                Contact.organization_id == shop_id, 
                Contact.type == 'supplier',
                Contact.is_deleted == False
            ).first()
            if any_supplier:
                supplier_id = any_supplier.id
                supplier_name = any_supplier.name
                
        return {
            "product_id": insight_record.product_id,
            "insight": insight_record.insight,
            "recommended_action": insight_record.recommended_action,
            "confidence_score": insight_record.confidence_score,
            "predicted_daily_demand": insight_record.predicted_daily_demand,
            "suggested_supplier_id": supplier_id,
            "suggested_supplier_name": supplier_name
        }
    
    # Fallback if cron hasn't run yet
    return {
        "product_id": product_id,
        "insight": "Analyzing Data",
        "recommended_action": "Check back tomorrow for AI insights after nightly job.",
        "confidence_score": 0,
        "predicted_daily_demand": 0.0
    }
