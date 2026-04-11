import { useState } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from './StateSpinners';

export default function PredictionWidget({ shopId, productId }) {
  const [prediction, setPrediction] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchInsights = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await axiosClient.get(`/api/v1/predictions/${productId}?shop_id=${shopId}&window_size_days=14`);
      setPrediction(response.data);
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

  const isHealthy = prediction.suggested_order_qty === 0;

  return (
    <div style={{ padding: '1rem', border: '1px solid #ccc', borderRadius: '8px', background: isHealthy ? '#e7f9eb' : '#fff3cd' }}>
      <h4 style={{ margin: '0 0 0.5rem 0' }}>Demand Logic Engine</h4>
      <p style={{ margin: '0.2rem 0' }}><strong>Action:</strong> <span style={{ color: isHealthy ? 'green' : 'red' }}>{prediction.action_required}</span></p>
      <p style={{ margin: '0.2rem 0' }}>Est. Daily Sales: {prediction.predicted_daily_demand.toFixed(2)}</p>
      <p style={{ margin: '0.2rem 0' }}>Target Safety Buffer: {prediction.safety_stock_required.toFixed(0)}</p>
    </div>
  );
}
