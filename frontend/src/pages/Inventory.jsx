import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import PredictionWidget from '../components/PredictionWidget';
import { LoadingSpinner, ErrorState, EmptyState } from '../components/StateSpinners';
import { formatCurrency } from '../utils';

// --- Availability Badge ---
function AvailabilityBadge({ qty, threshold = 5 }) {
  let label, bg, color;
  if (qty <= 0) {
    label = 'Out of Stock';
    bg = '#fef2f2';
    color = '#dc2626';
  } else if (qty <= threshold) {
    label = 'Low Stock';
    bg = '#fffbeb';
    color = '#d97706';
  } else {
    label = 'In Stock';
    bg = '#f0fdf4';
    color = '#16a34a';
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '3px 10px', borderRadius: '999px', fontSize: '0.75rem',
      fontWeight: 700, background: bg, color: color, border: `1px solid ${color}22`,
      letterSpacing: '0.02em', textTransform: 'uppercase'
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        background: color, display: 'inline-block'
      }} />
      {label}
    </span>
  );
}

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
          const threshold = item.low_stock_threshold || reorderLimit || 5;

          return (
            <div key={item.product_id} className="card" style={{ border: `2px solid ${qty <= 0 ? '#fecaca' : qty <= threshold ? '#fde68a' : '#eee'}`, borderRadius: '12px', padding: '16px', display: 'flex', justifyContent: 'space-between', backgroundColor: '#fff', boxShadow: '0 4px 12px rgba(0,0,0,0.2)', transition: '0.2s', marginBottom: '1rem' }}>
              <div>
                <h3 style={{ margin: '0', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  {item.name} <span style={{ fontSize: '0.8rem', color: '#888' }}>({item.sku})</span>
                  <AvailabilityBadge qty={qty} threshold={threshold} />
                </h3>
                <p style={{ margin: '0.5rem 0', fontWeight: 'bold', color: qty <= 0 ? '#dc2626' : qty <= threshold ? '#d97706' : '#16a34a' }}>
                  Current Stock: {qty}
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
