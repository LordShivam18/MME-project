import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import Navigation from '../components/Navigation';
import PredictionWidget from '../components/PredictionWidget';
import { LoadingSpinner, ErrorState, EmptyState } from '../components/StateSpinners';

export default function Dashboard() {
  const [products, setProducts] = useState([]);
  const [inventoryDetails, setInventoryDetails] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Hardcoded for MVP Auth extraction.
  const shopId = 1; 

  const fetchDashboardData = async () => {
    setIsLoading(true);
    try {
      // 1. Fetch Master Products
      const prodRes = await axiosClient.get(`/products/?shop_id=${shopId}&limit=50`);
      const fetchedProducts = prodRes.data;
      setProducts(fetchedProducts);

      // 2. Fetch specific dynamic inventory levels for each product concurrently
      const inventoryMap = {};
      const invPromises = fetchedProducts.map(p => 
        axiosClient.get(`/inventory/${p.id}?shop_id=${shopId}`).catch(e => null)
      );
      const invResults = await Promise.all(invPromises);
      
      fetchedProducts.forEach((p, idx) => {
        if (invResults[idx] && invResults[idx].data) {
          inventoryMap[p.id] = invResults[idx].data;
        }
      });
      setInventoryDetails(inventoryMap);

    } catch (err) {
      setError("Failed to load dashboard data over secure network.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      <Navigation />
      
      <h2>Real-Time Inventory Status</h2>
      <p style={{ color: '#666' }}>Review active stock quantities and ping the Math Engine for restock suggestions.</p>
      
      {isLoading && <LoadingSpinner />}
      {error && <ErrorState message={error} />}
      {!isLoading && products.length === 0 && !error && (
        <EmptyState message="Your shop is completely empty!" suggestion="Head to 'Manage Products' to establish your first vendor SKU." />
      )}

      <div style={{ display: 'grid', gap: '1rem', marginTop: '2rem' }}>
        {products.map(product => {
          const inv = inventoryDetails[product.id];
          const qty = inv ? inv.quantity_on_hand : 0;
          const reorderLimit = inv ? inv.reorder_point : 0;
          const isLowStock = qty <= reorderLimit;

          return (
            <div key={product.id} style={{ border: `2px solid ${isLowStock ? '#ffcccc' : '#eee'}`, borderRadius: '8px', padding: '1.5rem', display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: '0' }}>{product.name} <span style={{ fontSize: '0.8rem', color: '#888' }}>({product.sku})</span></h3>
                <p style={{ margin: '0.5rem 0', fontWeight: 'bold', color: isLowStock ? 'red' : 'green' }}>
                  Current Stock: {qty} {isLowStock && "⚠️ (CRITICAL LEVEL)"}
                </p>
                <div style={{ fontSize: '0.9rem', color: '#555', marginTop: '1rem' }}>
                   Base Price: ${product.base_price.toFixed(2)} | Category: {product.category}
                </div>
              </div>
              
              <div style={{ width: '350px' }}>
                 {/* LAZY LOADED PREDICTION ENGINE */}
                 <PredictionWidget shopId={shopId} productId={product.id} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
