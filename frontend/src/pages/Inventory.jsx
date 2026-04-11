import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import Navigation from '../components/Navigation';
import PredictionWidget from '../components/PredictionWidget';
import { LoadingSpinner, ErrorState, EmptyState } from '../components/StateSpinners';

export default function Inventory() {
  const [summaryData, setSummaryData] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const shopId = 1; 

  const fetchSummary = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get(`/api/v1/inventory/summary?shop_id=${shopId}&limit=100`);
      setSummaryData(res.data);
    } catch (err) {
      setError("Failed to load inventory data. Check backend connection.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, []);

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      <Navigation />
      
      <h2>Real-Time Inventory Status</h2>
      <p style={{ color: '#666' }}>Review active stock quantities and ping the ML Engine exclusively when required.</p>
      
      {isLoading && <LoadingSpinner />}
      {error && <ErrorState message={error} />}
      {!isLoading && summaryData.length === 0 && !error && (
        <EmptyState message="Your catalog is completely empty!" suggestion="Head to 'Manage Products' to establish your first vendor SKU." />
      )}

      <div style={{ display: 'grid', gap: '1rem', marginTop: '2rem' }}>
        {summaryData.map(item => {
          const qty = item.quantity_on_hand;
          const reorderLimit = item.reorder_point;
          const isLowStock = qty <= reorderLimit;

          return (
            <div key={item.product_id} style={{ border: `2px solid ${isLowStock ? '#ffcccc' : '#eee'}`, borderRadius: '8px', padding: '1.5rem', display: 'flex', justifyContent: 'space-between', backgroundColor: '#fff' }}>
              <div>
                <h3 style={{ margin: '0' }}>{item.name} <span style={{ fontSize: '0.8rem', color: '#888' }}>({item.sku})</span></h3>
                <p style={{ margin: '0.5rem 0', fontWeight: 'bold', color: isLowStock ? 'red' : 'green' }}>
                  Current Stock: {qty} {isLowStock && "⚠️ (REORDER NOW)"}
                </p>
                <div style={{ fontSize: '0.9rem', color: '#555', marginTop: '1rem' }}>
                   Base Price: ${item.base_price.toFixed(2)} | Category: {item.category}
                </div>
              </div>
              
              <div style={{ width: '350px' }}>
                 <PredictionWidget shopId={shopId} productId={item.product_id} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
