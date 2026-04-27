import logging
import json
from sqlalchemy.orm import Session
from models.core import Product, Inventory, Sale, ProductInsight, Contact, Order, OrderItem
from logic_engine import SupplierScorer
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

        # 2. Supplier Ranking Engine
        # Get raw orders data for SupplierScorer
        orders_data_raw = db.query(
            Contact.id.label('contact_id'),
            Contact.name.label('contact_name'),
            Order.created_at,
            Order.expected_delivery_date,
            Order.status,
            Product.lead_time_days
        ).join(Order, Order.contact_id == Contact.id)\
         .join(OrderItem, OrderItem.order_id == Order.id)\
         .join(Product, Product.id == OrderItem.product_id)\
         .filter(
            OrderItem.product_id == product_id,
            Contact.organization_id == shop_id,
            Contact.type == 'supplier'
         ).all()

        formatted_orders_data = []
        for r in orders_data_raw:
            delivered_at = None
            if r.status == 'delivered':
                # proxy for delivered at
                delivered_at = r.expected_delivery_date or r.created_at + timedelta(days=r.lead_time_days or 7)
                
            formatted_orders_data.append({
                'id': r.contact_id,
                'name': r.contact_name,
                'created_at': r.created_at,
                'delivered_at': delivered_at,
                'lead_time_days': r.lead_time_days or 7
            })

        ranked_suppliers = SupplierScorer.rank_suppliers(formatted_orders_data)
        
        if not ranked_suppliers:
            # Fallback to any active supplier
            general_suppliers = db.query(Contact).filter(
                Contact.organization_id == shop_id, 
                Contact.type == 'supplier',
                Contact.is_deleted == False
            ).order_by(Contact.created_at.desc()).limit(3).all()
            
            for s in general_suppliers:
                ranked_suppliers.append({"id": s.id, "name": s.name, "score": 0.0})

        # Process JSON fields
        try:
            anomaly_flags = json.loads(insight_record.anomaly_flags) if insight_record.anomaly_flags else []
        except:
            anomaly_flags = []
            
        try:
            weekday_pattern = json.loads(insight_record.weekday_pattern) if insight_record.weekday_pattern else {}
        except:
            weekday_pattern = {}

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
            "reorder_suggestion_source": "Historical Analytics + Core AI Engine",
            
            # AI Engine Upgrades
            "demand_min": getattr(insight_record, 'demand_min', 0.0) or 0.0,
            "demand_max": getattr(insight_record, 'demand_max', 0.0) or 0.0,
            "stockout_risk": getattr(insight_record, 'stockout_risk', "none") or "none",
            "overstock_risk": getattr(insight_record, 'overstock_risk', "none") or "none",
            "is_dead_stock": getattr(insight_record, 'is_dead_stock', False) or False,
            "anomaly_flags": anomaly_flags,
            "weekday_pattern": weekday_pattern,
            "generated_at": getattr(insight_record, 'generated_at', None),
            "model_version": getattr(insight_record, 'model_version', "1.0.0") or "1.0.0"
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
        "reorder_suggestion_source": "Pending initial scan",
        
        # AI Engine Upgrades
        "demand_min": 0.0,
        "demand_max": 0.0,
        "stockout_risk": "none",
        "overstock_risk": "none",
        "is_dead_stock": False,
        "anomaly_flags": [],
        "weekday_pattern": {},
        "generated_at": None,
        "model_version": "1.0.0"
    }
