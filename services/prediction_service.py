import logging
from sqlalchemy.orm import Session
from models.core import Product, Inventory, Sale, ProductInsight, Contact, Order, OrderItem
from schemas.core import PredictionResponse
from sqlalchemy import func
from datetime import datetime, timedelta

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
        # 1. Live Context Stats
        inv = db.query(Inventory).filter(Inventory.product_id == product_id, Inventory.shop_id == shop_id).first()
        current_stock = inv.quantity_on_hand if inv else 0
        
        cutoff = datetime.utcnow() - timedelta(days=7)
        recent_sales = db.query(func.sum(Sale.quantity_sold)).filter(
            Sale.product_id == product_id,
            Sale.sale_date >= cutoff
        ).scalar() or 0
        avg_daily = recent_sales / 7.0

        # Query last order quantity for comparison
        last_order = db.query(OrderItem).join(Order, OrderItem.order_id == Order.id).filter(
            OrderItem.product_id == product_id,
            Order.organization_id == shop_id,
            Order.is_deleted == False
        ).order_by(Order.created_at.desc()).first()
        last_order_qty = last_order.quantity if last_order else 0

        # 2. Supplier Ranking Engine (70% freq / 30% recency)
        orders_data = db.query(Contact.id, Contact.name, Order.created_at).\
            join(Order, Order.contact_id == Contact.id).\
            join(OrderItem, OrderItem.order_id == Order.id).\
            filter(OrderItem.product_id == product_id, Contact.organization_id == shop_id, Contact.type == 'supplier').all()
            
        supplier_metrics = {}
        for c_id, c_name, created_at in orders_data:
            if c_id not in supplier_metrics:
                supplier_metrics[c_id] = {"name": c_name, "freq": 0, "latest": created_at}
            supplier_metrics[c_id]["freq"] += 1
            if created_at > supplier_metrics[c_id]["latest"]:
                supplier_metrics[c_id]["latest"] = created_at
                
        ranked_suppliers = []
        if supplier_metrics:
            max_freq = max(s["freq"] for s in supplier_metrics.values())
            now = datetime.utcnow()
            for c_id, data in supplier_metrics.items():
                freq_score = (data["freq"] / max_freq) if max_freq > 0 else 0
                days_ago = (now - data["latest"]).days
                recency_score = max(0, (365 - days_ago) / 365.0)
                final_score = (freq_score * 0.70) + (recency_score * 0.30)
                
                ranked_suppliers.append({
                    "id": c_id,
                    "name": data["name"],
                    "score": final_score
                })
            ranked_suppliers.sort(key=lambda x: x["score"], reverse=True)
        else:
            # Fallback to any active supplier
            general_suppliers = db.query(Contact).filter(
                Contact.organization_id == shop_id, 
                Contact.type == 'supplier',
                Contact.is_deleted == False
            ).order_by(Contact.created_at.desc()).limit(3).all()
            
            for s in general_suppliers:
                ranked_suppliers.append({"id": s.id, "name": s.name, "score": 0.0})

        return {
            "product_id": insight_record.product_id,
            "insight": insight_record.insight,
            "recommended_action": insight_record.recommended_action,
            "confidence_score": insight_record.confidence_score,
            "predicted_daily_demand": insight_record.predicted_daily_demand,
            "current_stock_quantity": current_stock,
            "avg_daily_sales": avg_daily,
            "last_order_quantity": last_order_qty,
            "recommended_suppliers": ranked_suppliers,
            "reorder_suggestion_source": "Historical Analytics + Core AI Engine"
        }
    
    # Fallback if cron hasn't run yet
    return {
        "product_id": product_id,
        "insight": "Analyzing Data",
        "recommended_action": "Check back tomorrow for AI insights after nightly job.",
        "confidence_score": 0,
        "predicted_daily_demand": 0.0,
        "current_stock_quantity": 0,
        "avg_daily_sales": 0.0,
        "last_order_quantity": 0,
        "recommended_suppliers": [],
        "reorder_suggestion_source": "Pending initial scan"
    }
