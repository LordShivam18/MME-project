"""
Core Logic Engine for Inventory and Demand Prediction System
Pure Python MVP Implementation.
"""
import math

class DataSanitizer:
    @staticmethod
    def validate_and_clean(sales_data: list) -> list:
        """
        Validates sales data.
        Handles negative values by flooring to 0.
        Handles None (missing) by imputing with previous value or 0.
        """
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

    # Removed mitigate_spikes hard capping!
    # Spikes represent real demand and should be preserved in historical data
    # to accurately calculate variance/safety stock. We instead handle them via weight modulation.


class DemandPredictor:
    @staticmethod
    def simple_moving_average(sales_data: list, window: int = 7) -> float:
        if not sales_data:
            return 0.0
        window_data = sales_data[-window:]
        return sum(window_data) / len(window_data)

    @staticmethod
    def adaptive_weighted_moving_average(sales_data: list, base_weights: list, spike_threshold: float = 1.5) -> float:
        """
        Calculates WMA but dynamically reduces the weight of unnatural spikes.
        This preserves the data pattern while preventing sudden massive over-predictions.
        """
        if not sales_data or not base_weights:
            return 0.0
        
        window = len(base_weights)
        window_data = sales_data[-window:] if len(sales_data) >= window else ([0] * (window - len(sales_data)) + sales_data)
            
        # Calculate mean & stdev purely for spike identification
        avg_sales = sum(window_data) / len(window_data)
        variance = sum((x - avg_sales) ** 2 for x in window_data) / len(window_data)
        stdev = math.sqrt(variance)
        
        upper_bound = avg_sales + (spike_threshold * stdev)
        
        # Modulate weights: If it's a spike, halve its voting power.
        adjusted_weights = []
        for val, weight in zip(window_data, base_weights):
            if stdev > 0 and val > upper_bound:
                adjusted_weights.append(weight * 0.5) # Penalty factor
            else:
                adjusted_weights.append(weight)
                
        # Re-normalize weights so they sum to exactly 1.0 again
        weight_sum = sum(adjusted_weights)
        normalized_weights = [w / weight_sum for w in adjusted_weights] if weight_sum > 0 else base_weights
        
        return sum(val * weight for val, weight in zip(window_data, normalized_weights))


class InventoryLogic:
    @staticmethod
    def calculate_safety_stock(sales_data: list, avg_lead_time_days: int, service_factor: float = 1.65) -> float:
        """
        Calculates safety stock based on demand variability (Standard Deviation).
        service_factor: 1.65 represents approx 95% service level (confidence we won't stock out).
        Formula: Z * Demand_StdDev * sqrt(Lead_Time)
        """
        if not sales_data or len(sales_data) < 2:
            return 0.0
            
        avg_sales = sum(sales_data) / len(sales_data)
        variance = sum((x - avg_sales) ** 2 for x in sales_data) / (len(sales_data) - 1)  # Sample variance
        demand_std_dev = math.sqrt(variance)
        
        safety_stock = service_factor * demand_std_dev * math.sqrt(avg_lead_time_days)
        return max(0.0, safety_stock)

    @staticmethod
    def calculate_reorder_point(predicted_daily_demand: float, lead_time_days: int, safety_stock: float) -> float:
        """
        Calculates the EXACT inventory level at which a new order should be placed.
        Formula: (Lead Time Demand) + Safety Stock
        """
        return (predicted_daily_demand * lead_time_days) + safety_stock

    @staticmethod
    def suggest_order_quantity(current_inventory: float, reorder_point: float, 
                               predicted_daily_demand: float, lead_time_days: int) -> float:
        """
        Adaptive ordering logic entirely independent of rigid 'Review Periods'.
        Instead of targeting fixed days, it dynamically targets covering the lead time + 
        the next cycle (usually 1.5x to 2x lead time) dependent on system velocity.
        """
        if current_inventory > reorder_point:
            return 0.0  
        
        # Adaptive Target: Order enough to survive the lead time delay, PLUS enough to last 
        # a subsequent full cycle before dipping back to safety stock. 
        # Using 1.5x lead time as a dynamic restock cycle multiplier.
        dynamic_restock_cycle = lead_time_days * 1.5 
        
        target_inventory_level = reorder_point + (predicted_daily_demand * dynamic_restock_cycle)
        order_quantity = target_inventory_level - current_inventory
        
        return max(0.0, order_quantity)



