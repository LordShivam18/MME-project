import { useState } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from './StateSpinners';
import SalesChart from './SalesChart';

export default function PredictionWidget({ shopId, productId, onReorder }) {
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

  const isHealthy = prediction.prediction !== "Increase stock";

  return (
    <div style={{ padding: '1rem', border: '1px solid #ccc', borderRadius: '8px', background: isHealthy ? '#e7f9eb' : '#fff3cd' }}>
      <h4 style={{ margin: '0 0 0.5rem 0' }}>Demand Logic Engine</h4>
      <p style={{ margin: '0.2rem 0' }}><strong>Action:</strong> <span style={{ color: isHealthy ? 'green' : 'red' }}>{prediction.prediction}</span></p>
      <p style={{ margin: '0.2rem 0' }}>Est. Daily Sales: {(prediction?.estimated_daily_sales ?? 0).toFixed(2)}</p>
      <p style={{ margin: '0.2rem 0' }}>Target Safety Buffer: {(prediction?.target_safety_buffer ?? 0).toFixed(0)}</p>
      {prediction?.reorder_now && (
        <button onClick={() => onReorder && onReorder(productId, prediction?.target_safety_buffer)} style={{ backgroundColor: "red", color: "white", padding: "0.4rem 0.8rem", border: "none", borderRadius: "4px", marginTop: "0.5rem", cursor: "pointer", fontWeight: 'bold', display: 'block' }}>
          Reorder Now
        </button>
      )}
      <div>
         <SalesChart data={chartData} />
      </div>
    </div>
  );
}
