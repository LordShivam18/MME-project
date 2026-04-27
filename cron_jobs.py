import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
from database import SessionLocal
from models.core import Product, Inventory, Sale, ProductInsight, Notification
from logic_engine import DemandPredictor, RiskAnalyzer, AnomalyDetector, ConfidenceScorer, ProductProfiler

logger = logging.getLogger(__name__)

def run_daily_ai_insights():
    """
    CRON JOB: Runs daily to precompute AI insights for all products.
    Uses up to 30 days of sales history and new AI engine components.
    """
    db: Session = SessionLocal()
    try:
        logger.info("Starting background AI insight computation for all products.")
        products = db.query(Product).filter(Product.is_deleted == False).all()
        
        for product in products:
            # Get 30-day recent sales
            cutoff_30d = datetime.utcnow() - timedelta(days=30)
            
            sales_records = db.query(Sale).filter(
                Sale.product_id == product.id,
                Sale.sale_date >= cutoff_30d
            ).order_by(Sale.sale_date.asc()).all()
            
            # Map sales to a continuous daily array for the last 30 days
            sales_by_date = {}
            for s in sales_records:
                date_str = s.sale_date.strftime("%Y-%m-%d")
                sales_by_date[date_str] = sales_by_date.get(date_str, 0) + s.quantity_sold
                
            sales_data_30d = []
            for i in range(29, -1, -1):
                d_str = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
                sales_data_30d.append(sales_by_date.get(d_str, 0))
                
            # If no sales at all in 30 days, it's mostly 0
            if not any(sales_data_30d):
                recent_avg = 0.0
            else:
                recent_avg = sum(sales_data_30d[-7:]) / 7.0
                
            # 1. Demand Prediction
            mean_demand, min_demand, max_demand = DemandPredictor.calculate_wma(sales_data_30d, window=14)
            weekday_multipliers = DemandPredictor.get_weekday_multipliers()
            
            # 2. Risk Analysis
            inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
            qoh = inv.quantity_on_hand if inv else 0
            lead_time = product.lead_time_days or 7
            
            stockout_risk = RiskAnalyzer.analyze_stockout_risk(qoh, mean_demand, lead_time)
            overstock_risk = RiskAnalyzer.analyze_overstock_risk(qoh, mean_demand, max_months=3.0)
            
            # Dead stock: last sale days ago
            last_sale = db.query(Sale).filter(Sale.product_id == product.id).order_by(Sale.sale_date.desc()).first()
            last_sale_days_ago = (datetime.utcnow() - last_sale.sale_date).days if last_sale else 999
            
            # avg days between sales
            days_between = 10.0
            if len(sales_records) > 1:
                total_days = (sales_records[-1].sale_date - sales_records[0].sale_date).days
                days_between = total_days / (len(sales_records) - 1)
                if days_between <= 0: days_between = 1.0
                
            is_dead_stock = RiskAnalyzer.analyze_dead_stock(sales_data_30d, last_sale_days_ago, days_between)
            
            # 3. Anomaly Detection
            anomalies = AnomalyDetector.detect_anomalies(sales_data_30d, threshold_z=2.5)
            anomaly_flags = json.dumps([f"Day {a['index']} (Val: {a['value']}, Z: {a['z_score']})" for a in anomalies]) if anomalies else json.dumps([])
            
            # 4. Confidence Score
            confidence = ConfidenceScorer.calculate_confidence(sales_data_30d, last_sale_days_ago)
            
            # 5. Product Profiler
            profile = ProductProfiler.classify_product(sales_data_30d, product.selling_price, product.cost_price)
            
            
            # Construct insights text
            insight_text = "Stable Demand"
            action_text = "Maintain inventory levels"
            
            if is_dead_stock:
                insight_text = "Dead Stock Detected"
                action_text = "Discount or liquidate inventory"
            elif stockout_risk in ["high", "critical"]:
                insight_text = f"Critical Stockout Risk ({stockout_risk})"
                action_text = "Restock immediately"
            elif overstock_risk in ["high", "medium"]:
                insight_text = "Overstock Risk"
                action_text = "Delay next reorder"
            elif recent_avg > mean_demand * 1.5 and mean_demand > 0:
                insight_text = "High Demand Surge"
                action_text = "Increase reorder quantity"
                
            # Notifications for stockout risk
            if stockout_risk in ["high", "critical"]:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                recent_notif = db.query(Notification).filter(
                    Notification.organization_id == product.shop_id,
                    Notification.type == "insight",
                    Notification.message.like(f"%{product.name}%"),
                    Notification.created_at >= cutoff_time
                ).first()
                if not recent_notif:
                    notif = Notification(
                        organization_id=product.shop_id,
                        type="insight",
                        priority="high",
                        message=f"AI Alert: {product.name} is at critical stockout risk."
                    )
                    db.add(notif)
            
            # Upsert insight record
            insight_record = db.query(ProductInsight).filter(ProductInsight.product_id == product.id).first()
            if not insight_record:
                insight_record = ProductInsight(
                    product_id=product.id,
                    organization_id=product.shop_id,
                )
                db.add(insight_record)
            
            insight_record.insight = insight_text
            insight_record.recommended_action = action_text
            insight_record.confidence_score = confidence
            insight_record.predicted_daily_demand = mean_demand
            
            insight_record.demand_min = min_demand
            insight_record.demand_max = max_demand
            insight_record.stockout_risk = stockout_risk
            insight_record.overstock_risk = overstock_risk
            insight_record.is_dead_stock = is_dead_stock
            insight_record.anomaly_flags = anomaly_flags
            insight_record.weekday_pattern = json.dumps(weekday_multipliers)
            insight_record.product_behavior_profile = profile
            insight_record.last_profile_updated_at = datetime.utcnow()
            insight_record.generated_at = datetime.utcnow()
            insight_record.model_version = "1.1.0"
            
            db.commit()
            
        logger.info("Background AI insight computation successfully completed.")
    except Exception as e:
        logger.error(f"Error during AI insight cron job: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_daily_ai_insights()
