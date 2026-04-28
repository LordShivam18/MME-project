import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import PredictionWidget from '../components/PredictionWidget';
import { LoadingSpinner, ErrorState, EmptyState } from '../components/StateSpinners';
import { formatCurrency } from '../utils';

export default function Inventory() {
  const [summaryData, setSummaryData] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const shopId = 1; 

  const fetchSummary = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get(`/api/v1/inventory/summary?shop_id=${shopId}&limit=100`);
      setSummaryData(res.data || []);
    } catch (err) {
      console.error(err);
      setSummaryData([]);
      setError("Failed to load inventory data. Check backend connection.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, []);

  const handleAddStock = async (product_id, recommended_qty) => {
    const qtyStr = window.prompt("Enter quantity to add:", recommended_qty || "");
    if (!qtyStr) return;
    const quantity = parseInt(qtyStr, 10);
    if (isNaN(quantity) || quantity <= 0) return;
    
    try {
      setIsLoading(true);
      await axiosClient.post(`/api/v1/inventory/add-stock`, { product_id, quantity });
      fetchSummary();
    } catch(err) {
      setError("Failed to add stock");
      setIsLoading(false);
    }
  };

  if (!summaryData) return <p>Loading...</p>;

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      
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
            <div key={item.product_id} className="card" style={{ border: `2px solid ${isLowStock ? '#ffcccc' : '#eee'}`, borderRadius: '12px', padding: '16px', display: 'flex', justifyContent: 'space-between', backgroundColor: '#fff', boxShadow: '0 4px 12px rgba(0,0,0,0.2)', transition: '0.2s', marginBottom: '1rem' }}>
              <div>
                <h3 style={{ margin: '0' }}>{item.name} <span style={{ fontSize: '0.8rem', color: '#888' }}>({item.sku})</span></h3>
                <p style={{ margin: '0.5rem 0', fontWeight: 'bold', color: isLowStock ? 'red' : 'green' }}>
                  Current Stock: {qty} {isLowStock && (
                    <span style={{ background: "red", color: "white", padding: "4px", borderRadius: "4px", marginLeft: "0.5rem", fontSize: "0.8rem" }}>
                      LOW STOCK
                    </span>
                  )}
                </p>
                <div style={{ fontSize: '0.9rem', color: '#555', marginTop: '1rem' }}>
                   Selling Price: {formatCurrency(item.selling_price)} | Category: {item.category}
                </div>
              </div>
              
              <div style={{ width: '350px' }}>
                 <PredictionWidget shopId={shopId} productId={item.product_id} onReorder={handleAddStock} />
              </div>
            </div>
          );
        })}
      </div>
      <style>{`
        .card:hover { transform: scale(1.02); }
      `}</style>
    </div>
  );
}
