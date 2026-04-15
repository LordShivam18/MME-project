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
  const [sellingPrice, setSellingPrice] = useState(0);
  const [leadTime, setLeadTime] = useState(1);
  const [successMessage, setSuccessMessage] = useState('');
  const [editingProductId, setEditingProductId] = useState(null);

  const clearMsg = () => {
    setFormError('');
    setSuccessMessage('');
  };

  const fetchProducts = async () => {
    setIsLoading(true);
    try {
      // Cleaned up query logic since shop_id is automatically pulled via backend tokens securely
      const res = await axiosClient.get(`/api/v1/products/?limit=50`);
      setProducts(res.data || []);
    } catch (err) {
      console.error(err);
      setProducts([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts();
  }, []);

  const handleAddProduct = async (e) => {
    e.preventDefault();
    clearMsg();

    // Native Frontend Data Validation
    if (costPrice <= 0 || sellingPrice <= 0) {
      setFormError("Prices must be greater than zero.");
      return;
    }
    if (name.length < 2 || sku.length < 3) {
      setFormError("Name/SKU texts are too short to be valid.");
      return;
    }

    try {
      setIsLoading(true);
      const payload = {
        name,
        sku,
        category,
        cost_price: Number(costPrice),
        selling_price: Number(sellingPrice),
        lead_time_days: Number(leadTime)
      };
      
      if (editingProductId) {
        console.log("UPDATE:", editingProductId);
        await axiosClient.put(`/api/v1/products/${editingProductId}`, payload);
        setSuccessMessage("Product updated successfully");
        setEditingProductId(null);
      } else {
        await axiosClient.post("/api/v1/products/", payload);
        setSuccessMessage("Product added successfully");
      }
      
      // Clear form and refetch bounds
      setName(''); setSku(''); setCategory(''); setCostPrice(0); setSellingPrice(0); setLeadTime(1);
      await fetchProducts();
    } catch (err) {
      console.error("Product operation error:", err);
      // Properly extract the FastAPI schema validation message blocks if embedded
      let errorMsg = "Something went wrong";
      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMsg = err.response.data.detail;
        } else {
          errorMsg = JSON.stringify(err.response.data.detail);
        }
      }
      setFormError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEditClick = (p) => {
    clearMsg();
    setEditingProductId(p.id);
    setName(p.name);
    setSku(p.sku);
    setCategory(p.category);
    setCostPrice(p.cost_price || 0);
    setSellingPrice(p.selling_price || 0);
    setLeadTime(p.lead_time_days || 1);
  };

  const handleDelete = async (id) => {
    try {
      clearMsg();
      setIsLoading(true);
      console.log("DELETE:", `/api/v1/products/${id}`);
      await axiosClient.delete(`/api/v1/products/${id}`);
      setSuccessMessage("Product deleted successfully");
      await fetchProducts();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Something went wrong");
      setIsLoading(false);
    }
  };

  const handleSale = async (product_id) => {
    try {
      clearMsg();
      console.log("SALE:", product_id);
      const res = await axiosClient.post(`/api/v1/sales/`, {
        product_id: product_id,
        quantity_sold: 1
      });
      setSuccessMessage(`Sale recorded! Stock left: ${res.data.stock_left}`);
      await fetchProducts();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Internal error");
    }
  };

  const handleAddStock = async (product_id) => {
    const qtyStr = window.prompt("Enter quantity to add:");
    if (!qtyStr) return;
    const quantity = parseInt(qtyStr, 10);
    if (isNaN(quantity) || quantity <= 0) {
      setFormError("Invalid quantity");
      return;
    }

    try {
      clearMsg();
      setIsLoading(true);
      const res = await axiosClient.post(`/api/v1/inventory/add-stock`, {
         product_id: product_id,
         quantity: quantity
      });
      setSuccessMessage(`Stock updated! New quantity: ${res.data.quantity_on_hand}`);
      await fetchProducts();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Internal error");
      setIsLoading(false);
    }
  };

  if (!products) return <p>Loading...</p>;

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      <Navigation />
      
      <div style={{ display: 'flex', gap: '2rem' }}>
        {/* CREATE PRODUCT FORM */}
        <div style={{ flex: '1', padding: '1.5rem', background: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: '8px' }}>
          <h3>Catalog New Vendor Product</h3>
          {formError && <ErrorState message={formError} />}
          {successMessage && <div style={{ background: '#d4edda', color: '#155724', padding: '0.8rem', borderRadius: '4px', marginBottom: '1rem' }}>{successMessage}</div>}
          
          <form onSubmit={handleAddProduct} style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            <input placeholder="Product Name" value={name} onChange={e => { clearMsg(); setName(e.target.value); }} required style={{ padding: '0.3rem' }} />
            <input placeholder="Supplier SKU (Unique)" value={sku} onChange={e => { clearMsg(); setSku(e.target.value); }} required style={{ padding: '0.3rem' }} />
            <input placeholder="System Category" value={category} onChange={e => { clearMsg(); setCategory(e.target.value); }} required style={{ padding: '0.3rem' }} />
            
            <div style={{ display: 'flex', gap: '1rem' }}>
              <label>Cost Price:<input type="number" step="0.01" value={costPrice} onChange={e => { clearMsg(); setCostPrice(e.target.value); }} required style={{ width: '100%' }} /></label>
              <label>Selling Price:<input type="number" step="0.01" value={sellingPrice} onChange={e => { clearMsg(); setSellingPrice(e.target.value); }} required style={{ width: '100%' }} /></label>
            </div>
            
            <label>Vendor Lead Time (Days):
              <input type="number" value={leadTime} onChange={e => { clearMsg(); setLeadTime(e.target.value); }} required style={{ width: '100%' }} />
            </label>
            
            <button type="submit" disabled={isLoading} style={{ opacity: isLoading ? 0.7 : 1, background: '#28a745', color: 'white', padding: '0.5rem', border: 'none', cursor: 'pointer', marginTop: '1rem' }}>
              {editingProductId ? "Update Product" : "Add Product to Catalog"}
            </button>
            {editingProductId && (
              <button type="button" onClick={() => { clearMsg(); setEditingProductId(null); }} style={{ background: '#6c757d', color: 'white', padding: '0.5rem', border: 'none', cursor: 'pointer', marginTop: '0.5rem' }}>
                Cancel Edit
              </button>
            )}
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
                        <td style={{ padding: '0.5rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <button onClick={() => handleEditClick(p)} style={{ padding: '0.3rem 0.6rem', background: '#ffc107', borderRadius: '4px', border: 'none', cursor: 'pointer' }}>Edit</button>
                          <button onClick={() => handleDelete(p.id)} style={{ padding: '0.3rem 0.6rem', background: '#dc3545', color: 'white', borderRadius: '4px', border: 'none', cursor: 'pointer' }}>Delete</button>
                          <button onClick={() => handleSale(p.id)} style={{ padding: '0.3rem 0.6rem', background: '#0dcaf0', borderRadius: '4px', border: 'none', cursor: 'pointer' }}>Record Sale</button>
                          <button onClick={() => handleAddStock(p.id)} style={{ padding: '0.3rem 0.6rem', background: '#28a745', color: 'white', borderRadius: '4px', border: 'none', cursor: 'pointer' }}>Add Stock</button>
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
