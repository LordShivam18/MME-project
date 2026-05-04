import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

export default function Marketplace() {
  const [stores, setStores] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedStore, setSelectedStore] = useState(null);
  const [products, setProducts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [productsLoading, setProductsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStores();
  }, []);

  const fetchStores = async (q = '') => {
    setIsLoading(true);
    try {
      const params = q ? `?search=${encodeURIComponent(q)}` : '';
      const res = await axiosClient.get(`/api/v1/public/stores${params}`);
      setStores(res.data?.stores || []);
    } catch (err) {
      setStores([]);
      setError('Failed to load stores');
    } finally {
      setIsLoading(false);
    }
  };

  const openStore = async (store) => {
    setSelectedStore(store);
    setProductsLoading(true);
    try {
      const res = await axiosClient.get(`/api/v1/public/products?store_id=${store.id}`);
      setProducts(res.data);
    } catch (err) {
      setProducts([]);
    } finally {
      setProductsLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchStores(search);
  };

  if (selectedStore) {
    return (
      <div style={s.page}>
        <button onClick={() => setSelectedStore(null)} style={s.backBtn}>← Back to Stores</button>
        
        <div style={s.storeHeader}>
          <div style={s.storeAvatar}>{selectedStore.name?.[0] || '?'}</div>
          <div>
            <h1 style={s.storeTitle}>{selectedStore.name}</h1>
            {selectedStore.category && <span style={s.badge}>{selectedStore.category}</span>}
          </div>
        </div>

        <div style={s.storeInfo}>
          {selectedStore.address && <div style={s.infoItem}><span>📍</span> {selectedStore.address}</div>}
          {selectedStore.phone && <div style={s.infoItem}><span>📞</span> {selectedStore.phone}</div>}
          <div style={s.infoItem}><span>📦</span> {selectedStore.product_count} products</div>
        </div>

        <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: '#0f172a', margin: '2rem 0 1rem' }}>Products</h2>

        {productsLoading ? <LoadingSpinner /> : (
          <div style={s.productGrid}>
            {products.length === 0 ? (
              <div style={{ gridColumn: '1 / -1', textAlign: 'center', color: '#94a3b8', padding: '3rem' }}>No products available</div>
            ) : products.map(p => (
              <div key={p.id} style={s.productCard}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <h3 style={{ margin: 0, fontSize: '1rem', color: '#1e293b', fontWeight: 600 }}>{p.name}</h3>
                  <span style={{
                    ...s.stockBadge,
                    backgroundColor: p.availability === 'in_stock' ? '#d1fae5' : p.availability === 'low_stock' ? '#fef3c7' : '#fee2e2',
                    color: p.availability === 'in_stock' ? '#065f46' : p.availability === 'low_stock' ? '#92400e' : '#991b1b',
                  }}>
                    {p.availability === 'in_stock' ? '✓ In Stock' : p.availability === 'low_stock' ? '⚠ Low Stock' : '✗ Out of Stock'}
                  </span>
                </div>
                {p.category && <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.25rem' }}>{p.category}</div>}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0f172a' }}>₹{p.selling_price?.toFixed(2) || '0.00'}</span>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>{p.stock_quantity} units</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={s.page}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>Marketplace</h1>
          <p style={{ color: '#64748b', margin: '0.25rem 0 0 0', fontSize: '0.95rem' }}>Discover stores and browse products</p>
        </div>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            style={s.searchInput}
            placeholder="Search stores..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <button type="submit" style={s.searchBtn}>Search</button>
        </form>
      </div>

      {isLoading ? <LoadingSpinner /> : error ? <ErrorState message={error} /> : (
        <div style={s.storeGrid}>
          {stores.length === 0 ? (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '4rem 2rem', color: '#94a3b8' }}>
              <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🏪</div>
              <h3 style={{ color: '#64748b' }}>No stores found</h3>
              <p>Check back later or try a different search</p>
            </div>
          ) : stores.map(store => (
            <div key={store.id} style={s.storeCard} onClick={() => openStore(store)}>
              <div style={s.storeCardAvatar}>{store.name?.[0] || '?'}</div>
              <h3 style={{ margin: '0.75rem 0 0.25rem', fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>{store.name}</h3>
              {store.category && <span style={{ ...s.badge, fontSize: '0.75rem' }}>{store.category}</span>}
              
              {/* Rating + Trust */}
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '0.5rem' }}>
                {store.total_reviews > 0 && (
                  <span style={{ fontSize: '0.85rem', color: '#f59e0b', fontWeight: 700 }}>
                    ⭐ {store.rating}
                    <span style={{ color: '#94a3b8', fontWeight: 400, fontSize: '0.75rem' }}> ({store.total_reviews})</span>
                  </span>
                )}
                {store.trust_score > 0 && (
                  <span style={{ fontSize: '0.75rem', color: '#059669', fontWeight: 600, padding: '1px 6px', backgroundColor: '#d1fae5', borderRadius: '4px' }}>
                    Trusted {Math.round(store.trust_score * 100)}%
                  </span>
                )}
              </div>

              {/* Trust Breakdown */}
              {store.trust_breakdown && store.trust_score > 0 && (
                <div style={{ marginTop: '0.5rem', padding: '0.4rem 0.6rem', backgroundColor: '#f0fdf4', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                  <div style={{ fontSize: '0.65rem', color: '#64748b', fontWeight: 600, marginBottom: '3px' }}>Why this score?</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px', fontSize: '0.7rem', color: '#475569' }}>
                    <span>📊 Rating: {Math.round(store.trust_breakdown.rating * 100)}%</span>
                    <span>📦 Delivery: {Math.round(store.trust_breakdown.delivery * 100)}%</span>
                    <span>🤝 Fairness: {Math.round(store.trust_breakdown.fairness * 100)}%</span>
                    <span>⚡ Activity: {Math.round(store.trust_breakdown.activity * 100)}%</span>
                  </div>
                </div>
              )}

              <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#64748b' }}>
                {store.address && <div>📍 {store.address}</div>}
                <div style={{ marginTop: '0.5rem', fontWeight: 600, color: '#3b82f6' }}>{store.product_count} products →</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const s = {
  page: { fontFamily: '"Inter", sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1.5rem' },
  searchInput: { padding: '0.6rem 1rem', border: '1px solid #d1d5db', borderRadius: '8px', fontSize: '0.9rem', width: '220px', outline: 'none' },
  searchBtn: { padding: '0.6rem 1.25rem', backgroundColor: '#0f172a', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' },
  storeGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' },
  storeCard: { backgroundColor: '#fff', borderRadius: '12px', padding: '1.5rem', border: '1px solid #e2e8f0', cursor: 'pointer', transition: 'all 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' },
  storeCardAvatar: { width: '48px', height: '48px', borderRadius: '12px', backgroundColor: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem', fontWeight: 700, color: '#3b82f6' },
  backBtn: { background: 'none', border: 'none', color: '#3b82f6', fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem', padding: 0, marginBottom: '1rem' },
  storeHeader: { display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' },
  storeAvatar: { width: '56px', height: '56px', borderRadius: '14px', backgroundColor: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.8rem', fontWeight: 700, color: '#3b82f6' },
  storeTitle: { margin: 0, fontSize: '1.5rem', fontWeight: 800, color: '#0f172a' },
  badge: { display: 'inline-block', padding: '2px 10px', backgroundColor: '#f1f5f9', color: '#475569', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600 },
  storeInfo: { display: 'flex', gap: '1.5rem', flexWrap: 'wrap', padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '10px', border: '1px solid #e2e8f0' },
  infoItem: { display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', color: '#475569' },
  productGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' },
  productCard: { backgroundColor: '#fff', borderRadius: '10px', padding: '1.25rem', border: '1px solid #e2e8f0', transition: 'box-shadow 0.2s' },
  stockBadge: { padding: '2px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap' },
};
