import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from './StateSpinners';
import SalesChart from './SalesChart';

export default function PredictionWidget({ shopId, productId, onReorder }) {
  const navigate = useNavigate();
  const [prediction, setPrediction] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchInsights = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await axiosClient.get(`/api/v1/predictions/${productId}?shop_id=${shopId}&window_size_days=14`);
      setPrediction(response.data);
      const chartRes = await axiosClient.get(`/api/v1/sales/history/${productId}`);
      setChartData(chartRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Calculation failed.");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} />;

  if (!prediction) {
    return (
      <button onClick={fetchInsights} style={{ background: '#0d6efd', color: 'white', padding: '0.5rem 1rem', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        Run AI Demand Prediction
      </button>
    );
  }

  const isHealthy = prediction.insight === "Stable Demand";

  return (
    <div style={{ padding: '1.5rem', border: '2px solid', borderColor: isHealthy ? '#10b981' : '#3b82f6', borderRadius: '12px', background: isHealthy ? '#f0fdf4' : '#eff6ff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <h4 style={{ margin: 0, color: '#1f2937' }}>AI Insight</h4>
        <div style={{ background: '#10b981', color: 'white', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 'bold' }}>
          {prediction.confidence_score}% Confidence
        </div>
      </div>
      <h3 style={{ margin: '0.5rem 0', color: isHealthy ? '#065f46' : '#1e40af', fontSize: '1.25rem' }}>{prediction.insight}</h3>
      <p style={{ margin: '0.2rem 0', color: '#6b7280', fontSize: '0.9rem' }}>Est. Daily Demand: {(Number(prediction?.predicted_daily_demand || 0)).toFixed(2)} units</p>
      
      <div style={{ marginTop: '1rem', padding: '1rem', background: '#ffffff', borderRadius: '8px', borderLeft: '4px solid #3b82f6' }}>
        <strong style={{ display: 'block', marginBottom: '0.25rem', color: '#374151' }}>Reasoning Data:</strong>
        <ul style={{ color: '#4b5563', margin: '0.5rem 0', paddingLeft: '1.2rem', fontSize: '0.9rem' }}>
          <li>Current Stock: <strong>{prediction.current_stock_quantity} units</strong></li>
          <li>Recent Avg Sales: <strong>{prediction.avg_daily_sales?.toFixed(2)} / day</strong></li>
          <li>Predicted Demand: <strong>{prediction.predicted_daily_demand?.toFixed(2)} / day</strong> ({(prediction.predicted_daily_demand > prediction.avg_daily_sales ? '+' : '')}{((prediction.predicted_daily_demand - prediction.avg_daily_sales) / (prediction.avg_daily_sales || 1) * 100).toFixed(0)}% shift vs last 7 days)</li>
        </ul>
        <strong style={{ display: 'block', marginTop: '0.5rem', marginBottom: '0.25rem', color: '#374151' }}>Recommended Action ({prediction.reorder_suggestion_source}):</strong>
        <span style={{ color: '#4b5563', fontSize: '0.9rem' }}>{prediction.recommended_action}</span>
        
        {prediction.recommended_suppliers && prediction.recommended_suppliers.length > 0 && (
          <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#6b7280' }}>
            <strong>Top Recommended Supplier:</strong> {prediction.recommended_suppliers[0].name}
          </div>
        )}
      </div>

      <button onClick={() => {
        navigate('/contacts', { 
          state: { 
            prefill_product: productId, 
            quantity: Math.ceil((prediction.predicted_daily_demand || 1) * 7),
            insight_suppliers: prediction.recommended_suppliers || []
          } 
        });
      }} style={{ backgroundColor: "#3b82f6", color: "white", padding: "0.6rem 1rem", border: "none", borderRadius: "8px", marginTop: "1rem", cursor: "pointer", fontWeight: 'bold', width: '100%' }}>
        View Suppliers
      </button>
      <div>
         <SalesChart data={chartData} />
      </div>
    </div>
  );
}
