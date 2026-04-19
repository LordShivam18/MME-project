import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import SessionLocal
from models.core import Product, Inventory, Sale, ProductInsight, Notification

logger = logging.getLogger(__name__)

def run_daily_ai_insights():
    """
    CRON JOB: Runs daily to precompute AI insights for all products.
    Uses 7-day moving average and trend detection based on previous window.
    """
    db: Session = SessionLocal()
    try:
        logger.info("Starting background AI insight computation for all products.")
        products = db.query(Product).filter(Product.is_deleted == False).all()
        
        for product in products:
            # Get 7-day recent sales
            cutoff_recent = datetime.utcnow() - timedelta(days=3)
            cutoff_previous = datetime.utcnow() - timedelta(days=7)
            
            # Simple aggregations
            sales = db.query(Sale).filter(Sale.product_id == product.id).all()
            if not sales:
                continue

            # Calculate Moving Averages (last 3 days vs previous 4 days in a 7 day window)
            recent_sales = [s for s in sales if s.sale_date >= cutoff_recent]
            previous_sales = [s for s in sales if cutoff_previous <= s.sale_date < cutoff_recent]
            
            recent_total = sum(s.quantity_sold for s in recent_sales)
            previous_total = sum(s.quantity_sold for s in previous_sales)
            
            recent_avg = recent_total / 3.0 if recent_total else 0
            previous_avg = previous_total / 4.0 if previous_total else 0
            
            trend_score = 0
            if previous_avg > 0:
                trend_score = (recent_avg - previous_avg) / previous_avg
            elif recent_avg > 0:
                trend_score = 1.0  # Infinite growth spike
                
            insight_text = "Stable Demand"
            action_text = "Maintain inventory levels"
            confidence = 80
            
            # Inventory context
            inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
            qoh = inv.quantity_on_hand if inv else 0
            
            # Generate insights
            if trend_score > 0.5:
                # >50% jump in demand
                insight_text = "High Demand Surge"
                action_text = "Increase reorder quantity urgently"
                confidence = 90
            elif trend_score < -0.3:
                # >30% drop in demand
                insight_text = "Demand Dropping"
                action_text = "Delay next reorder to prevent overstock"
                confidence = 85
                
            # Stockout risk override
            predicted_daily = recent_avg if recent_avg > 0 else (sum(s.quantity_sold for s in sales[-14:]) / 14.0 if len(sales) > 0 else 0)
            if predicted_daily > 0 and qoh < (predicted_daily * 3):
                insight_text = "Critical Stockout Risk"
                action_text = f"Restock immediately (less than 3 days remaining)"
                confidence = 95
                
                # Check for existing stockout notification to avoid spam
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
                
            elif trend_score > 0.5:
                # Provide notification for high demand
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                recent_notif = db.query(Notification).filter(
                    Notification.organization_id == product.shop_id,
                    Notification.type == "insight",
                    Notification.created_at >= cutoff_time
                ).first()
                if not recent_notif:
                    notif = Notification(
                        organization_id=product.shop_id,
                        type="insight",
                        priority="medium",
                        message=f"AI Alert: {product.name} is experiencing a surge in demand."
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
            insight_record.predicted_daily_demand = predicted_daily
            
            db.commit()
            
        logger.info("Background AI insight computation successfully completed.")
    except Exception as e:
        logger.error(f"Error during AI insight cron job: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_daily_ai_insights()
