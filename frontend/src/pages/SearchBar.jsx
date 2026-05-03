import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner } from '../components/StateSpinners';

const SORT_OPTIONS = [
  { value: 'relevance', label: '🎯 Relevance' },
  { value: 'price_asc', label: '💰 Price: Low → High' },
  { value: 'price_desc', label: '💎 Price: High → Low' },
  { value: 'demand', label: '📈 Demand' },
];

const AVAIL_COLORS = {
  in_stock: { bg: '#d1fae5', color: '#065f46', label: '✓ In Stock' },
  low_stock: { bg: '#fef3c7', color: '#92400e', label: '⚠ Low Stock' },
  out_of_stock: { bg: '#fee2e2', color: '#991b1b', label: '✗ Out of Stock' },
};

export default function SearchBar() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [sortBy, setSortBy] = useState('relevance');
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    setIsLoading(true);
    setSearched(true);
    try {
      const params = new URLSearchParams();
      if (query) params.set('q', query);
      if (category) params.set('category', category);
      if (minPrice) params.set('min_price', minPrice);
      if (maxPrice) params.set('max_price', maxPrice);
      params.set('sort_by', sortBy);
      params.set('limit', '30');

      const res = await axiosClient.get(`/api/v1/public/search?${params.toString()}`);
      setResults(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-search on mount
  useEffect(() => { handleSearch(); }, []);

  return (
    <div style={s.page}>
      <div style={s.headerSection}>
        <h1 style={s.title}>🔍 Product Search</h1>
        <p style={s.subtitle}>Discover products across all public stores</p>
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSearch} style={s.searchForm}>
        <div style={s.searchRow}>
          <input
            style={s.mainInput}
            placeholder="Search products..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <button type="submit" style={s.searchBtn}>Search</button>
        </div>

        <div style={s.filterRow}>
          <input
            style={s.filterInput}
            placeholder="Category"
            value={category}
            onChange={e => setCategory(e.target.value)}
          />
          <div style={s.priceRange}>
            <input
              style={s.priceInput}
              type="number"
              placeholder="Min ₹"
              value={minPrice}
              onChange={e => setMinPrice(e.target.value)}
            />
            <span style={{ color: '#94a3b8' }}>—</span>
            <input
              style={s.priceInput}
              type="number"
              placeholder="Max ₹"
              value={maxPrice}
              onChange={e => setMaxPrice(e.target.value)}
            />
          </div>
          <select style={s.sortSelect} value={sortBy} onChange={e => { setSortBy(e.target.value); }}>
            {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </form>

      {/* Results */}
      {isLoading ? <LoadingSpinner /> : (
        <>
          {searched && (
            <div style={{ marginBottom: '1rem', fontSize: '0.9rem', color: '#64748b' }}>
              {results.length} product{results.length !== 1 ? 's' : ''} found
            </div>
          )}
          <div style={s.grid}>
            {results.length === 0 && searched ? (
              <div style={s.empty}>
                <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔎</div>
                <h3 style={{ color: '#64748b' }}>No products found</h3>
                <p style={{ color: '#94a3b8' }}>Try adjusting your filters</p>
              </div>
            ) : results.map(p => {
              const avail = AVAIL_COLORS[p.availability] || AVAIL_COLORS.out_of_stock;
              return (
                <div key={p.product_id} style={s.card}>
                  <div style={s.cardHeader}>
                    <h3 style={s.prodName}>{p.name}</h3>
                    <span style={{ ...s.availBadge, backgroundColor: avail.bg, color: avail.color }}>
                      {avail.label}
                    </span>
                  </div>
                  {p.category && <div style={s.catBadge}>{p.category}</div>}
                  {p.ranking_reason && (
                    <div style={{ fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600, marginBottom: '0.5rem' }}>
                      💡 {p.ranking_reason}
                    </div>
                  )}
                  
                  <div style={s.cardBody}>
                    <div style={s.priceTag}>₹{p.price?.toFixed(2)}</div>
                    <div style={s.storeName}>🏪 {p.store_name}</div>
                  </div>

                  <div style={s.scoreRow}>
                    <div style={s.scoreItem}>
                      <span style={s.scoreLabel}>Demand</span>
                      <div style={s.scoreBar}>
                        <div style={{ ...s.scoreFill, width: `${Math.min(p.demand_score * 100, 100)}%`, backgroundColor: '#3b82f6' }} />
                      </div>
                    </div>
                    <div style={s.scoreItem}>
                      <span style={s.scoreLabel}>Relevance</span>
                      <div style={s.scoreBar}>
                        <div style={{ ...s.scoreFill, width: `${Math.min(p.relevance_score * 100, 100)}%`, backgroundColor: '#10b981' }} />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

const s = {
  page: { fontFamily: '"Inter", sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1.5rem' },
  headerSection: { marginBottom: '1.5rem' },
  title: { fontSize: '1.5rem', fontWeight: 800, color: '#0f172a', margin: 0 },
  subtitle: { color: '#64748b', margin: '0.25rem 0 0 0', fontSize: '0.9rem' },
  searchForm: { marginBottom: '1.5rem' },
  searchRow: { display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' },
  mainInput: { flex: 1, padding: '0.75rem 1rem', border: '1px solid #d1d5db', borderRadius: '10px', fontSize: '1rem', outline: 'none' },
  searchBtn: { padding: '0.75rem 1.5rem', backgroundColor: '#0f172a', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem' },
  filterRow: { display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' },
  filterInput: { padding: '0.5rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '0.9rem', outline: 'none', width: '140px' },
  priceRange: { display: 'flex', gap: '0.5rem', alignItems: 'center' },
  priceInput: { padding: '0.5rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '0.9rem', outline: 'none', width: '90px' },
  sortSelect: { padding: '0.5rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '0.9rem', outline: 'none', cursor: 'pointer', backgroundColor: '#fff' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' },
  card: { backgroundColor: '#fff', borderRadius: '12px', padding: '1.25rem', border: '1px solid #e2e8f0', transition: 'box-shadow 0.2s' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' },
  prodName: { margin: 0, fontSize: '1rem', fontWeight: 700, color: '#0f172a', flex: 1 },
  availBadge: { padding: '2px 8px', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 600, whiteSpace: 'nowrap', marginLeft: '0.5rem' },
  catBadge: { display: 'inline-block', padding: '1px 8px', backgroundColor: '#f1f5f9', color: '#64748b', borderRadius: '4px', fontSize: '0.75rem', marginBottom: '0.75rem' },
  cardBody: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' },
  priceTag: { fontSize: '1.3rem', fontWeight: 800, color: '#0f172a' },
  storeName: { fontSize: '0.8rem', color: '#64748b' },
  scoreRow: { display: 'flex', gap: '1rem' },
  scoreItem: { flex: 1, display: 'flex', flexDirection: 'column', gap: '3px' },
  scoreLabel: { fontSize: '0.7rem', color: '#94a3b8', fontWeight: 600 },
  scoreBar: { height: '5px', backgroundColor: '#e5e7eb', borderRadius: '3px', overflow: 'hidden' },
  scoreFill: { height: '100%', borderRadius: '3px', transition: 'width 0.3s' },
  empty: { gridColumn: '1 / -1', textAlign: 'center', padding: '4rem 2rem', backgroundColor: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' },
};
