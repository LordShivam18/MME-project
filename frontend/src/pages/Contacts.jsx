import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import Navigation from '../components/Navigation';

export default function Contacts() {
  const location = useLocation();
  const [contacts, setContacts] = useState([]);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedContact, setSelectedContact] = useState(null);
  const [globalOrders, setGlobalOrders] = useState([]);
  const [orders, setOrders] = useState([]);

  // Create Mode states
  const [isCreatingContact, setIsCreatingContact] = useState(false);
  const [newContact, setNewContact] = useState({ name: '', phone: '', type: 'customer' });
  
  const [isCreatingOrder, setIsCreatingOrder] = useState(false);
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]); // { product, quantity }
  const [selectedProduct, setSelectedProduct] = useState('');
  const [selectedQty, setSelectedQty] = useState(1);

  const fetchContacts = async () => {
    try {
      const res = await axiosClient.get('/api/v1/contacts');
      setContacts(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchProducts = async () => {
    try {
      const res = await axiosClient.get('/api/v1/products/');
      setProducts(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchOrders = async (contactId) => {
    try {
      const res = await axiosClient.get(`/api/v1/contacts/${contactId}/orders`);
      setOrders(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchGlobalOrders = async () => {
    try {
      const res = await axiosClient.get(`/api/v1/orders`);
      setGlobalOrders(res.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchContacts();
    fetchProducts();
    fetchGlobalOrders();
  }, []);

  // Handle auto-routing from PredictionWidget
  useEffect(() => {
    if (contacts.length > 0 && products.length > 0 && location.state?.supplier_id && !selectedContact) {
      const prefillSupplier = contacts.find(c => c.id === location.state.supplier_id);
      if (prefillSupplier) {
        setSelectedContact(prefillSupplier);
        setIsCreatingOrder(true);
        
        const prefillProduct = products.find(p => p.id === location.state.prefill_product);
        if (prefillProduct && cart.length === 0) {
          setCart([{ product: prefillProduct, quantity: location.state.quantity }]);
        }
      }
    }
  }, [contacts, products, location.state]);

  useEffect(() => {
    if (selectedContact) {
      fetchOrders(selectedContact.id);
    } else {
      setOrders([]);
    }
  }, [selectedContact]);

  const handleCreateContact = async (e) => {
    e.preventDefault();
    try {
      await axiosClient.post('/api/v1/contacts', newContact);
      setIsCreatingContact(false);
      setNewContact({ name: '', phone: '', type: 'customer' });
      fetchContacts();
    } catch (err) { alert('Failed to create contact'); }
  };

  const handleAddToCart = () => {
    if (!selectedProduct) return;
    const product = products.find(p => p.id == selectedProduct);
    if (!product) return;
    
    setCart([...cart, { product, quantity: parseInt(selectedQty) }]);
    setSelectedProduct('');
    setSelectedQty(1);
  };

  const submitOrder = async () => {
    if (cart.length === 0 || !selectedContact) return;
    try {
      await axiosClient.post('/api/v1/orders', {
        contact_id: selectedContact.id,
        items: cart.map(c => ({ product_id: c.product.id, quantity: c.quantity }))
      });
      setIsCreatingOrder(false);
      setCart([]);
      fetchOrders(selectedContact.id);
    } catch (err) {
      alert('Failed to place order: ' + (err.response?.data?.detail || err.message));
    }
  };

  const updateOrderStatus = async (orderId, newStatus) => {
    try {
      await axiosClient.patch(`/api/v1/orders/${orderId}/status`, { status: newStatus });
      fetchOrders(selectedContact.id);
      fetchGlobalOrders();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update status');
    }
  };

  const filteredContacts = contacts.filter(c => {
    const matchesSearch = c.name.toLowerCase().includes(search.toLowerCase());
    const matchesType = typeFilter === 'all' || c.type === typeFilter;
    return matchesSearch && matchesType;
  });
  
  const cartTotal = cart.reduce((acc, c) => acc + (c.product.selling_price * c.quantity), 0);

  // Dashboard calculations
  const totalValue = globalOrders.reduce((acc, o) => acc + o.total_amount, 0);
  const pendingCount = globalOrders.filter(o => ['pending', 'confirmed'].includes(o.status)).length;
  const deliveredCount = globalOrders.filter(o => o.status === 'delivered').length;

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1400px', margin: '0 auto', padding: '1rem', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navigation />
      
      {/* Global Orders Dashboard */}
      <div style={{ display: 'flex', gap: '2rem', marginBottom: '2rem', padding: '1rem', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 'bold' }}>TOTAL SPEND/REVENUE</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#0f172a' }}>${totalValue.toFixed(2)}</div>
        </div>
        <div style={{ flex: 1, borderLeft: '1px solid #e2e8f0', paddingLeft: '2rem' }}>
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 'bold' }}>PENDING ORDERS</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#d97706' }}>{pendingCount}</div>
        </div>
        <div style={{ flex: 1, borderLeft: '1px solid #e2e8f0', paddingLeft: '2rem' }}>
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 'bold' }}>DELIVERED</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#10b981' }}>{deliveredCount}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '2rem', flex: 1, overflow: 'hidden' }}>
        
        {/* LEFT PANEL: Contacts */}
        <div style={{ borderRight: '1px solid #e5e7eb', paddingRight: '1rem', display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0 }}>Contacts</h2>
            <button onClick={() => setIsCreatingContact(!isCreatingContact)} style={styles.btnSm}>+ Add</button>
          </div>
          
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
             <select style={{...styles.input, marginBottom: 0, width: '100px'}} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="all">All</option>
                <option value="supplier">Suppliers</option>
                <option value="customer">Customers</option>
             </select>
             <input 
               type="text" 
               placeholder="Search..." 
               value={search} 
               onChange={(e) => setSearch(e.target.value)} 
               style={{...styles.input, marginBottom: 0, flex: 1}}
             />
          </div>
          
          {isCreatingContact && (
            <div style={{ marginTop: '1rem', padding: '1rem', background: '#f3f4f6', borderRadius: '8px' }}>
              <input style={styles.input} placeholder="Name" value={newContact.name} onChange={e => setNewContact({...newContact, name: e.target.value})} />
              <input style={styles.input} placeholder="Phone" value={newContact.phone} onChange={e => setNewContact({...newContact, phone: e.target.value})} />
              <select style={styles.input} value={newContact.type} onChange={e => setNewContact({...newContact, type: e.target.value})}>
                <option value="customer">Customer</option>
                <option value="supplier">Supplier</option>
              </select>
              <button onClick={handleCreateContact} style={{...styles.btn, width: '100%'}}>Save Contact</button>
            </div>
          )}

          <div style={{ marginTop: '1rem', overflowY: 'auto', flex: 1 }}>
            {filteredContacts.map(c => (
              <div 
                key={c.id} 
                onClick={() => { setSelectedContact(c); setIsCreatingOrder(false); }}
                style={{
                  padding: '1rem', 
                  borderBottom: '1px solid #f3f4f6', 
                  cursor: 'pointer',
                  backgroundColor: selectedContact?.id === c.id ? '#eff6ff' : 'white',
                  borderLeft: selectedContact?.id === c.id ? '4px solid #3b82f6' : '4px solid transparent'
                }}
              >
                <strong style={{ display: 'block', fontSize: '1.1rem' }}>{c.name}</strong>
                <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: '0.25rem' }}>
                  {c.type.toUpperCase()} | {c.phone || 'No phone'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT PANEL: Orders */}
        <div style={{ padding: '0 1rem', overflowY: 'auto' }}>
          {!selectedContact ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>
              <h2>Select a contact to view or create orders</h2>
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e5e7eb', paddingBottom: '1rem' }}>
                <div>
                  <h1 style={{ margin: '0 0 0.5rem 0' }}>{selectedContact.name}</h1>
                  <span style={{ padding: '0.2rem 0.5rem', background: '#e5e7eb', borderRadius: '4px', fontSize: '0.8rem' }}>{selectedContact.type}</span>
                </div>
                {!isCreatingOrder && (
                  <button onClick={() => setIsCreatingOrder(true)} style={{...styles.btn, background: '#10b981', color: 'white'}}>+ New Order</button>
                )}
              </div>

              {isCreatingOrder ? (
                <div style={{ marginTop: '2rem' }}>
                  <h2>Create New Order</h2>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', background: '#f9fafb', padding: '1rem', borderRadius: '8px' }}>
                    <div style={{ flex: 1 }}>
                      <label style={styles.label}>Product</label>
                      <select style={styles.input} value={selectedProduct} onChange={(e) => setSelectedProduct(e.target.value)}>
                        <option value="">-- Select Product --</option>
                        {products.map(p => <option key={p.id} value={p.id}>{p.name} (${p.selling_price})</option>)}
                      </select>
                    </div>
                    <div style={{ width: '100px' }}>
                      <label style={styles.label}>Qty</label>
                      <input type="number" min="1" value={selectedQty} onChange={(e) => setSelectedQty(e.target.value)} style={styles.input} />
                    </div>
                    <button onClick={handleAddToCart} style={styles.btnSecondary}>Add</button>
                  </div>

                  {cart.length > 0 && (
                    <div style={{ marginTop: '2rem', border: '1px solid #e5e7eb', borderRadius: '8px', overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                        <thead style={{ background: '#f3f4f6' }}>
                          <tr><th style={styles.th}>Item</th><th style={styles.th}>Qty</th><th style={styles.th}>Price</th><th style={styles.th}>Total</th></tr>
                        </thead>
                        <tbody>
                          {cart.map((item, idx) => (
                            <tr key={idx} style={{ borderBottom: '1px solid #e5e7eb' }}>
                              <td style={styles.td}>{item.product.name}</td>
                              <td style={styles.td}>{item.quantity}</td>
                              <td style={styles.td}>${item.product.selling_price}</td>
                              <td style={styles.td}>${item.product.selling_price * item.quantity}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div style={{ padding: '1rem', background: '#f9fafb', textAlign: 'right', fontSize: '1.2rem' }}>
                        <strong>Grand Total: ${cartTotal.toFixed(2)}</strong>
                      </div>
                      <div style={{ padding: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
                        <button onClick={() => setIsCreatingOrder(false)} style={styles.btnSecondary}>Cancel</button>
                        <button onClick={submitOrder} style={styles.btn}>Submit Checkout</button>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ marginTop: '2rem' }}>
                  {orders.length === 0 ? (
                    <p style={{ color: '#6b7280' }}>No historical orders for {selectedContact.name}.</p>
                  ) : (
                    orders.map(order => (
                      <div key={order.id} style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '1rem', marginBottom: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                          <div>
                            <strong>Order #{order.id}</strong>
                            <span style={{ marginLeft: '1rem', color: '#6b7280', fontSize: '0.9rem' }}>{new Date(order.created_at).toLocaleString()}</span>
                          </div>
                          <div>
                            <select 
                              value={order.status} 
                              onChange={(e) => updateOrderStatus(order.id, e.target.value)}
                              style={{...styles.input, margin: 0, padding: '0.2rem 0.5rem', width: 'auto'}}
                            >
                              <option value="pending">Pending</option>
                              <option value="confirmed">Confirmed</option>
                              <option value="shipped">Shipped</option>
                              <option value="delivered">Delivered</option>
                              <option value="cancelled">Cancelled</option>
                            </select>
                          </div>
                        </div>
                        <div style={{ background: '#f9fafb', padding: '0.5rem 1rem', borderRadius: '4px', fontSize: '0.9rem' }}>
                          {order.items?.length || 0} items — <strong>Total: ${Number(order.total_amount).toFixed(2)}</strong>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  input: {
    width: '100%',
    padding: '0.5rem',
    marginBottom: '0.5rem',
    border: '1px solid #d1d5db',
    borderRadius: '4px',
    boxSizing: 'border-box'
  },
  btn: {
    padding: '0.5rem 1rem',
    backgroundColor: '#3b82f6',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontWeight: 'bold'
  },
  btnSm: {
    padding: '0.25rem 0.5rem',
    backgroundColor: '#f3f4f6',
    border: '1px solid #d1d5db',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '0.8rem'
  },
  btnSecondary: {
    padding: '0.5rem 1rem',
    backgroundColor: '#6b7280',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer'
  },
  label: {
    display: 'block',
    fontSize: '0.8rem',
    fontWeight: 'bold',
    marginBottom: '0.25rem',
    color: '#374151'
  },
  th: { padding: '0.75rem', borderBottom: '2px solid #e5e7eb' },
  td: { padding: '0.75rem' }
};
