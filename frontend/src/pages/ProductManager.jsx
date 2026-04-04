import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import Navigation from '../components/Navigation';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

export default function ProductManager() {
  const [products, setProducts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [formError, setFormError] = useState('');
  const shopId = 1;

  // Form States
  const [name, setName] = useState('');
  const [sku, setSku] = useState('');
  const [category, setCategory] = useState('');
  const [costPrice, setCostPrice] = useState(0);
  const [basePrice, setBasePrice] = useState(0);
  const [leadTime, setLeadTime] = useState(1);

  const fetchProducts = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get(`/products/?shop_id=${shopId}&limit=50`);
      setProducts(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts();
  }, []);

  const handleAddProduct = async (e) => {
    e.preventDefault();
    setFormError('');

    // Native Frontend Data Validation (prevents pointless 422 API errors)
    if (costPrice <= 0 || basePrice <= 0) {
      setFormError("Prices must be greater than zero.");
      return;
    }
    if (name.length < 2 || sku.length < 3) {
      setFormError("Name/SKU texts are too short to be valid.");
      return;
    }

    try {
      await axiosClient.post(`/products/?shop_id=${shopId}`, {
        name, sku, category, cost_price: parseFloat(costPrice), base_price: parseFloat(basePrice), lead_time_days: parseInt(leadTime)
      });
      // Clear form and refetch bounds
      setName(''); setSku(''); setCategory(''); setCostPrice(0); setBasePrice(0); setLeadTime(1);
      fetchProducts();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Failed to create product in Database.");
    }
  };

  const handleSimulateSale = async (productId) => {
    try {
      const saleQty = parseInt(prompt("How many items did you sell just now? (Integer)"));
      if (!saleQty || saleQty <= 0) return alert("Sale aborted: Invalid amount.");

      // ACID Transaction endpoint
      await axiosClient.post(`/sales/?shop_id=${shopId}`, {
        product_id: productId,
        quantity_sold: saleQty,
        sale_price: 25.00 // Assuming standard price for MVP simulation
      });
      alert(`Sale of ${saleQty} items securely recorded in DB Ledger!`);
    } catch (err) {
      alert("SALE FAILED: " + (err.response?.data?.detail || "Internal error"));
    }
  };

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      <Navigation />
      
      <div style={{ display: 'flex', gap: '2rem' }}>
        {/* CREATE PRODUCT FORM */}
        <div style={{ flex: '1', padding: '1.5rem', background: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: '8px' }}>
          <h3>Catalog New Vendor Product</h3>
          {formError && <ErrorState message={formError} />}
          
          <form onSubmit={handleAddProduct} style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            <input placeholder="Product Name" value={name} onChange={e => setName(e.target.value)} required style={{ padding: '0.3rem' }} />
            <input placeholder="Supplier SKU (Unique)" value={sku} onChange={e => setSku(e.target.value)} required style={{ padding: '0.3rem' }} />
            <input placeholder="System Category" value={category} onChange={e => setCategory(e.target.value)} required style={{ padding: '0.3rem' }} />
            
            <div style={{ display: 'flex', gap: '1rem' }}>
              <label>Cost Price:<input type="number" step="0.01" value={costPrice} onChange={e => setCostPrice(e.target.value)} required style={{ width: '100%' }} /></label>
              <label>Selling Price:<input type="number" step="0.01" value={basePrice} onChange={e => setBasePrice(e.target.value)} required style={{ width: '100%' }} /></label>
            </div>
            
            <label>Vendor Lead Time (Days):
              <input type="number" value={leadTime} onChange={e => setLeadTime(e.target.value)} required style={{ width: '100%' }} />
            </label>
            
            <button type="submit" style={{ background: '#28a745', color: 'white', padding: '0.5rem', border: 'none', cursor: 'pointer', marginTop: '1rem' }}>Add Product to Catalog</button>
          </form>
        </div>

        {/* LIST PRODUCTS (PAGINATED MOCK) */}
        <div style={{ flex: '2' }}>
           <h3>Current Global Catalog</h3>
           {isLoading ? <LoadingSpinner /> : (
              <div style={{ border: '1px solid #eee' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead style={{ background: '#333', color: 'white' }}>
                    <tr>
                      <th style={{ padding: '0.5rem' }}>Name</th>
                      <th style={{ padding: '0.5rem' }}>Category</th>
                      <th style={{ padding: '0.5rem' }}>Lead Time</th>
                      <th style={{ padding: '0.5rem' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.map(p => (
                      <tr key={p.id} style={{ borderBottom: '1px solid #ddd' }}>
                        <td style={{ padding: '0.5rem' }}><strong>{p.name}</strong> <br/><small>{p.sku}</small></td>
                        <td style={{ padding: '0.5rem' }}>{p.category}</td>
                        <td style={{ padding: '0.5rem' }}>{p.lead_time_days} days</td>
                        <td style={{ padding: '0.5rem' }}>
                          <button onClick={() => handleSimulateSale(p.id)} style={{ padding: '0.3rem', background: '#0dcaf0', border: 'none', cursor: 'pointer' }}>Record Sale</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
           )}
        </div>
      </div>
    </div>
  );
}
