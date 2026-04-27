import logging
import json
from sqlalchemy.orm import Session
from models.core import Product, Inventory, Sale, ProductInsight, Contact, Order, OrderItem, Organization
from logic_engine import SupplierScorer, ExplainabilityEngine
from sqlalchemy import func
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def invalidate_prediction_cache(shop_id: int, product_id: int):
    # No longer needed - predictions are pre-computed daily via cron.
    pass

def get_product_prediction(db: Session, shop_id: int, product_id: int, window_size: int = 14, debug: bool = False):
    """Returns pre-computed AI insights from DB, achieving O(1) latency."""
    logger.info(f"Fetching precomputed AI insight for product_id: {product_id}")
    
    insight_record = db.query(ProductInsight).filter(
        ProductInsight.product_id == product_id,
        ProductInsight.organization_id == shop_id
    ).first()
    
    org = db.query(Organization).filter(Organization.id == shop_id).first()
    ai_decision_mode = org.ai_decision_mode if org else "balanced"
    
    multiplier = 1.0
    if ai_decision_mode == "conservative":
        multiplier = 1.2
    elif ai_decision_mode == "aggressive":
        multiplier = 0.85
        
    if insight_record:
        # Apply bias factor to the multiplier
        bias_factor = getattr(insight_record, 'bias_factor', 0.0) or 0.0
        final_multiplier = multiplier * (1 + bias_factor)
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

        explanation_points = ExplainabilityEngine.generate_explanation(insight_record, current_stock, avg_daily)

        debug_data = None
        if debug:
            cutoff_30d = datetime.utcnow() - timedelta(days=30)
            sales_records = db.query(Sale).filter(
                Sale.product_id == product_id,
                Sale.sale_date >= cutoff_30d
            ).order_by(Sale.sale_date.asc()).all()
            
            sales_by_date = {}
            for s in sales_records:
                date_str = s.sale_date.strftime("%Y-%m-%d")
                sales_by_date[date_str] = sales_by_date.get(date_str, 0) + s.quantity_sold
                
            sales_data_30d = []
            for i in range(29, -1, -1):
                d_str = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
                sales_data_30d.append(sales_by_date.get(d_str, 0))
                
            from logic_engine import DemandPredictor
            weights = DemandPredictor._get_exponential_weights(len(sales_data_30d[-14:]) if len(sales_data_30d[-14:]) > 0 else 0)
            
            debug_data = {
                "raw_sales_data": sales_data_30d,
                "weights_used": weights,
                "anomaly_flags": anomaly_flags,
                "risk_scores": {
                    "stockout": insight_record.stockout_risk,
                    "overstock": insight_record.overstock_risk,
                    "dead_stock": insight_record.is_dead_stock
                }
            }

        return {
            "product_id": insight_record.product_id,
            "insight": insight_record.insight,
            "recommended_action": insight_record.recommended_action,
            "confidence_score": insight_record.confidence_score,
            "predicted_daily_demand": insight_record.predicted_daily_demand * final_multiplier,
            "current_stock_quantity": current_stock,
            "avg_daily_sales": avg_daily,
            "last_order_quantity": last_order_qty,
            "recommended_suppliers": ranked_suppliers,
            "reorder_suggestion_source": "Historical Analytics + Core AI Engine",
            
            # AI Engine Upgrades
            "demand_min": (getattr(insight_record, 'demand_min', 0.0) or 0.0) * final_multiplier,
            "demand_max": (getattr(insight_record, 'demand_max', 0.0) or 0.0) * final_multiplier,
            "stockout_risk": getattr(insight_record, 'stockout_risk', "none") or "none",
            "overstock_risk": getattr(insight_record, 'overstock_risk', "none") or "none",
            "is_dead_stock": getattr(insight_record, 'is_dead_stock', False) or False,
            "anomaly_flags": anomaly_flags,
            "weekday_pattern": weekday_pattern,
            "product_behavior_profile": getattr(insight_record, 'product_behavior_profile', "standard") or "standard",
            "explanation_points": explanation_points,
            
            # Adaptive AI Upgrades
            "bias_factor": bias_factor,
            "adaptive_alpha": getattr(insight_record, 'adaptive_alpha', 0.3) or 0.3,
            "priority_score": getattr(insight_record, 'priority_score', 0.0) or 0.0,
            "priority_demand_norm": getattr(insight_record, 'priority_demand_norm', 0.0) or 0.0,
            "priority_margin_norm": getattr(insight_record, 'priority_margin_norm', 0.0) or 0.0,
            "priority_risk_norm": getattr(insight_record, 'priority_risk_norm', 0.0) or 0.0,
            
            "raw_debug_data": debug_data,
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
        "product_behavior_profile": "standard",
        "explanation_points": ["No AI insights available yet."],
        
        # Adaptive AI Upgrades
        "bias_factor": 0.0,
        "adaptive_alpha": 0.3,
        "priority_score": 0.0,
        "priority_demand_norm": 0.0,
        "priority_margin_norm": 0.0,
        "priority_risk_norm": 0.0,
        
        "raw_debug_data": None,
        "generated_at": None,
        "model_version": "1.0.0"
    }
