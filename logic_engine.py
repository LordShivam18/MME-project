"""
Core Logic Engine for Inventory and Demand Prediction System
Pure Python MVP Implementation.
"""
import math
from datetime import datetime
import json

class DataSanitizer:
    @staticmethod
    def validate_and_clean(sales_data: list) -> list:
        if not sales_data:
            return []
        cleaned = []
        for i, val in enumerate(sales_data):
            if val is None:
                cleaned.append(cleaned[-1] if cleaned else 0)
            elif val < 0:
                cleaned.append(0)
            else:
                cleaned.append(val)
        return cleaned

class DemandPredictor:
    @staticmethod
    def _get_exponential_weights(window: int, alpha: float = 0.3) -> list:
        weights = [(1 - alpha) ** i for i in range(window)]
        weights.reverse()
        total = sum(weights)
        return [w / total for w in weights]

    @staticmethod
    def calculate_wma(sales_data: list, window: int = 14) -> tuple:
        """
        Calculates Weighted Moving Average using exponential weights.
        Returns: (mean, min_demand, max_demand)
        """
        if not sales_data:
            return 0.0, 0.0, 0.0
            
        data = sales_data[-window:] if len(sales_data) >= window else sales_data
        window_size = len(data)
        
        if window_size == 0:
            return 0.0, 0.0, 0.0
            
        weights = DemandPredictor._get_exponential_weights(window_size)
        mean_demand = sum(val * w for val, w in zip(data, weights))
        
        # Calculate standard deviation for range
        variance = sum((x - mean_demand) ** 2 for x in data) / window_size
        std_dev = math.sqrt(variance)
        
        min_demand = max(0.0, mean_demand - std_dev)
        max_demand = mean_demand + std_dev
        
        return mean_demand, min_demand, max_demand

    @staticmethod
    def get_weekday_multipliers() -> dict:
        # Default static multipliers. Can be extended to accept per-product config.
        return {
            0: 1.0, # Monday
            1: 1.0, # Tuesday
            2: 1.0, # Wednesday
            3: 1.0, # Thursday
            4: 1.1, # Friday
            5: 1.3, # Saturday
            6: 0.7  # Sunday
        }

class RiskAnalyzer:
    @staticmethod
    def analyze_stockout_risk(current_stock: float, daily_demand: float, lead_time_days: int) -> str:
        if daily_demand <= 0:
            return "none"
        days_remaining = current_stock / daily_demand
        if days_remaining <= lead_time_days:
            return "critical"
        elif days_remaining <= lead_time_days * 1.5:
            return "high"
        elif days_remaining <= lead_time_days * 2:
            return "medium"
        elif days_remaining <= lead_time_days * 3:
            return "low"
        return "none"

    @staticmethod
    def analyze_overstock_risk(current_stock: float, daily_demand: float, max_months: float = 3.0) -> str:
        if daily_demand <= 0 and current_stock > 0:
            return "high" # Infinite overstock
        if daily_demand <= 0:
            return "none"
        months_of_supply = (current_stock / daily_demand) / 30.0
        if months_of_supply > max_months * 1.5:
            return "high"
        elif months_of_supply > max_months:
            return "medium"
        elif months_of_supply > max_months * 0.8:
            return "low"
        return "none"

    @staticmethod
    def analyze_dead_stock(sales_data: list, last_sale_days_ago: int, avg_days_between_sales: float = 10.0) -> bool:
        threshold = max(30.0, avg_days_between_sales * 3)
        return last_sale_days_ago >= threshold

class AnomalyDetector:
    @staticmethod
    def detect_anomalies(sales_data: list, threshold_z: float = 2.5) -> list:
        if not sales_data or len(sales_data) < 3:
            return []
            
        mean = sum(sales_data) / len(sales_data)
        variance = sum((x - mean) ** 2 for x in sales_data) / len(sales_data)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return []
            
        anomalies = []
        for i, val in enumerate(sales_data):
            z_score = abs(val - mean) / std_dev
            if z_score > threshold_z:
                anomalies.append({
                    "index": i,
                    "value": val,
                    "z_score": round(z_score, 2)
                })
        return anomalies

class ConfidenceScorer:
    @staticmethod
    def calculate_confidence(sales_data: list, last_sale_days_ago: int) -> int:
        score = 100
        n = len(sales_data)
        
        # Penalty 1: Insufficient data
        if n < 7:
            score -= 30
        elif n < 14:
            score -= 10
            
        # Penalty 2: High variance (Coefficient of Variation)
        if n > 0:
            mean = sum(sales_data) / n
            if mean > 0:
                variance = sum((x - mean) ** 2 for x in sales_data) / n
                std_dev = math.sqrt(variance)
                cv = std_dev / mean
                if cv > 1.0:
                    score -= 20
                elif cv > 0.5:
                    score -= 10
                    
        # Penalty 3: Stale data
        if last_sale_days_ago > 30:
            score -= 20
        elif last_sale_days_ago > 14:
            score -= 10
            
        return max(0, min(100, int(score)))

class SupplierScorer:
    @staticmethod
    def rank_suppliers(orders_data: list) -> list:
        """
        orders_data: list of dicts with:
        id, name, created_at, delivered_at, lead_time_days
        """
        supplier_metrics = {}
        for order in orders_data:
            c_id = order['id']
            if c_id not in supplier_metrics:
                supplier_metrics[c_id] = {"name": order['name'], "freq": 0, "latest": order['created_at'], "on_time_count": 0, "total_delivered": 0}
            
            supplier_metrics[c_id]["freq"] += 1
            if order['created_at'] > supplier_metrics[c_id]["latest"]:
                supplier_metrics[c_id]["latest"] = order['created_at']
                
            if order.get('delivered_at'):
                supplier_metrics[c_id]["total_delivered"] += 1
                days_taken = (order['delivered_at'] - order['created_at']).days
                if days_taken <= order.get('lead_time_days', 999):
                    supplier_metrics[c_id]["on_time_count"] += 1

        ranked_suppliers = []
        if supplier_metrics:
            max_freq = max(s["freq"] for s in supplier_metrics.values())
            now = datetime.utcnow()
            for c_id, data in supplier_metrics.items():
                freq_score = (data["freq"] / max_freq) if max_freq > 0 else 0
                days_ago = (now - data["latest"]).days
                recency_score = max(0, (365 - days_ago) / 365.0)
                
                reliability_score = (data["on_time_count"] / data["total_delivered"]) if data["total_delivered"] > 0 else 0.5
                
                final_score = (freq_score * 0.40) + (recency_score * 0.30) + (reliability_score * 0.30)
                
                ranked_suppliers.append({
                    "id": c_id,
                    "name": data["name"],
                    "score": final_score
                })
            ranked_suppliers.sort(key=lambda x: x["score"], reverse=True)
            
        return ranked_suppliers

class InventoryLogic:
    @staticmethod
    def calculate_safety_stock(sales_data: list, avg_lead_time_days: int, service_factor: float = 1.65) -> float:
        if not sales_data or len(sales_data) < 2:
            return 0.0
            
        avg_sales = sum(sales_data) / len(sales_data)
        variance = sum((x - avg_sales) ** 2 for x in sales_data) / (len(sales_data) - 1)
        demand_std_dev = math.sqrt(variance)
        
        safety_stock = service_factor * demand_std_dev * math.sqrt(max(0, avg_lead_time_days))
        return max(0.0, safety_stock)

    @staticmethod
    def calculate_reorder_point(predicted_daily_demand: float, lead_time_days: int, safety_stock: float) -> float:
        return (predicted_daily_demand * lead_time_days) + safety_stock

    @staticmethod
    def suggest_order_quantity(current_inventory: float, reorder_point: float, 
                               predicted_daily_demand: float, lead_time_days: int) -> float:
        if current_inventory > reorder_point:
            return 0.0  
        
        dynamic_restock_cycle = lead_time_days * 1.5 
        target_inventory_level = reorder_point + (predicted_daily_demand * dynamic_restock_cycle)
        order_quantity = target_inventory_level - current_inventory
        return max(0.0, order_quantity)

class ProductProfiler:
    @staticmethod
    def classify_product(sales_data: list, selling_price: float, cost_price: float) -> str:
        if not sales_data:
            return "standard"
            
        margin = selling_price - cost_price if selling_price and cost_price else 0
        margin_pct = (margin / selling_price) if selling_price else 0
        
        avg_daily_sales = sum(sales_data) / len(sales_data) if sales_data else 0
        
        if avg_daily_sales > 10:
            return "fast_moving"
        elif margin_pct < 0.15:
            return "low_margin"
        elif margin_pct > 0.5:
            return "high_margin"
            
        # Simplistic seasonality check: if variance is very high but sales are low on average
        mean = sum(sales_data) / len(sales_data)
        if mean > 0:
            variance = sum((x - mean) ** 2 for x in sales_data) / len(sales_data)
            cv = math.sqrt(variance) / mean
            if cv > 2.0 and mean > 2:
                return "seasonal"
                
        return "standard"

class ExplainabilityEngine:
    @staticmethod
    def generate_explanation(insight_record, current_stock: float, avg_daily_sales: float) -> list:
        points = []
        
        if not insight_record:
            return ["No AI insights available yet."]
            
        # 1. Demand Trend
        if insight_record.predicted_daily_demand > avg_daily_sales * 1.2:
            points.append(f"Demand is trending upwards. Predicted daily demand ({insight_record.predicted_daily_demand:.1f}) is higher than recent average ({avg_daily_sales:.1f}).")
        elif insight_record.predicted_daily_demand < avg_daily_sales * 0.8:
            points.append(f"Demand is trending downwards. Predicted daily demand ({insight_record.predicted_daily_demand:.1f}) is lower than recent average ({avg_daily_sales:.1f}).")
        else:
            points.append(f"Demand is stable at approximately {insight_record.predicted_daily_demand:.1f} units per day.")
            
        # 2. Stockout reasoning
        if insight_record.stockout_risk == "critical":
            points.append("Stockout risk is CRITICAL. Current stock will not cover the supplier lead time.")
        elif insight_record.stockout_risk == "high":
            points.append("Stockout risk is HIGH. Consider restocking immediately.")
        elif insight_record.stockout_risk == "none":
            points.append(f"Current stock levels ({current_stock} units) are sufficient.")
            
        # 3. Confidence reasoning
        confidence = getattr(insight_record, 'confidence_score', 0)
        if confidence > 80:
            points.append("High confidence in prediction due to stable and recent sales data.")
        elif confidence < 50:
            points.append("Low confidence in prediction due to irregular or stale sales data.")
            
        return points
