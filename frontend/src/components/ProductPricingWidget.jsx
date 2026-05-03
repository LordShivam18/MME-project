import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

/**
 * ProductPricingWidget — Shows bulk pricing tiers, smart price, and "Request Better Price" modal.
 * Drop into any product card/row.
 *
 * Props:
 *   productId: int (required)
 *   productName: string
 *   basePrice: number (selling_price)
 */
export default function ProductPricingWidget({ productId, productName, basePrice }) {
  const [tiers, setTiers] = useState([]);
  const [smartPrice, setSmartPrice] = useState(null);
  const [qty, setQty] = useState(1);
  const [showModal, setShowModal] = useState(false);
  const [reqPrice, setReqPrice] = useState('');
  const [reqQty, setReqQty] = useState('');
  const [submitMsg, setSubmitMsg] = useState('');
  const [loading, setLoading] = useState(false);

  // Fetch tiers on mount
  useEffect(() => {
    axiosClient.get(`/api/v1/pricing/tiers/${productId}`)
      .then(res => setTiers(res.data || []))
      .catch(() => setTiers([]));
  }, [productId]);

  // Fetch smart price when qty changes
  useEffect(() => {
    if (qty < 1) return;
    axiosClient.get(`/api/v1/products/${productId}/pricing?qty=${qty}`)
      .then(res => setSmartPrice(res.data))
      .catch(() => setSmartPrice(null));
  }, [productId, qty]);

  const handleSubmitRequest = async () => {
    if (!reqQty || !reqPrice || +reqQty < 1 || +reqPrice <= 0) {
      setSubmitMsg('Enter valid quantity and price');
      return;
    }
    setLoading(true);
    setSubmitMsg('');
    try {
      const res = await axiosClient.post('/api/v1/price-request', {
        product_id: productId,
        quantity: parseInt(reqQty),
        requested_price: parseFloat(reqPrice),
      });
      const d = res.data;
      if (d.status === 'accepted') {
        setSubmitMsg(`✅ Auto-accepted at ₹${d.approved_price}`);
      } else {
        setSubmitMsg(`📨 Request submitted (${d.risk_level || 'pending'}) — awaiting review`);
      }
      setReqPrice('');
      setReqQty('');
    } catch (err) {
      setSubmitMsg(err.response?.data?.detail || 'Failed to submit');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.container}>
      {/* Bulk Tiers */}
      {tiers.length > 0 && (
        <div style={s.tiersSection}>
          <div style={s.tiersTitle}>📦 Bulk Pricing</div>
          <div style={s.tiersList}>
            {tiers.map(t => (
              <div key={t.id} style={s.tierBadge}>
                {t.min_qty}+ → ₹{t.price_per_unit}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Smart Price Calculator */}
      <div style={s.calcSection}>
        <label style={s.label}>Qty:</label>
        <input
          type="number" min="1" value={qty}
          onChange={e => setQty(Math.max(1, +e.target.value))}
          style={s.qtyInput}
        />
        {smartPrice && (
          <div style={s.priceResult}>
            <span style={s.bestPrice}>₹{smartPrice.best_price}</span>
            {smartPrice.tier_applied && (
              <span style={s.savingsBadge}>Save ₹{smartPrice.savings}</span>
            )}
          </div>
        )}
      </div>

      {/* Upsell Suggestion */}
      {smartPrice?.suggestion && (
        <div style={s.suggestion}>💡 {smartPrice.suggestion}</div>
      )}

      {/* Negotiate Button */}
      <button onClick={() => { setShowModal(true); setSubmitMsg(''); }} style={s.negotiateBtn}>
        💬 Request Better Price
      </button>

      {/* Modal */}
      {showModal && (
        <div style={s.overlay} onClick={() => setShowModal(false)}>
          <div style={s.modal} onClick={e => e.stopPropagation()}>
            <h3 style={s.modalTitle}>Request Price for {productName}</h3>
            <p style={s.modalSub}>Base: ₹{basePrice} | We'll review your offer</p>
            <div style={s.formGroup}>
              <label style={s.label}>Quantity</label>
              <input type="number" min="1" value={reqQty} onChange={e => setReqQty(e.target.value)} style={s.input} placeholder="e.g. 50" />
            </div>
            <div style={s.formGroup}>
              <label style={s.label}>Your Price (₹/unit)</label>
              <input type="number" min="0.01" step="0.01" value={reqPrice} onChange={e => setReqPrice(e.target.value)} style={s.input} placeholder="e.g. 85.00" />
            </div>
            {submitMsg && <div style={{ ...s.msg, color: submitMsg.startsWith('✅') ? '#16a34a' : submitMsg.startsWith('📨') ? '#2563eb' : '#dc2626' }}>{submitMsg}</div>}
            <div style={s.btnRow}>
              <button onClick={() => setShowModal(false)} style={s.cancelBtn}>Cancel</button>
              <button onClick={handleSubmitRequest} disabled={loading} style={{ ...s.submitBtn, opacity: loading ? 0.6 : 1 }}>
                {loading ? 'Submitting...' : 'Submit Request'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const s = {
  container: { marginTop: '0.75rem', borderTop: '1px solid #f0f0f0', paddingTop: '0.75rem' },
  tiersSection: { marginBottom: '0.5rem' },
  tiersTitle: { fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.03em' },
  tiersList: { display: 'flex', gap: '6px', flexWrap: 'wrap' },
  tierBadge: { background: '#ede9fe', color: '#7c3aed', padding: '2px 8px', borderRadius: '6px', fontSize: '0.78rem', fontWeight: 600 },
  calcSection: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.5rem' },
  label: { fontSize: '0.8rem', fontWeight: 600, color: '#374151' },
  qtyInput: { width: 60, padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.85rem' },
  priceResult: { display: 'flex', alignItems: 'center', gap: 6 },
  bestPrice: { fontWeight: 700, fontSize: '1rem', color: '#111827' },
  savingsBadge: { background: '#dcfce7', color: '#16a34a', padding: '2px 8px', borderRadius: 999, fontSize: '0.72rem', fontWeight: 700 },
  suggestion: { fontSize: '0.78rem', color: '#d97706', background: '#fffbeb', padding: '4px 10px', borderRadius: 6, marginBottom: '0.5rem' },
  negotiateBtn: { width: '100%', padding: '6px 0', border: '1px solid #a78bfa', borderRadius: 8, background: '#f5f3ff', color: '#7c3aed', fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer', transition: '0.15s' },
  overlay: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 },
  modal: { background: '#fff', borderRadius: 16, padding: '2rem', width: 380, maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' },
  modalTitle: { margin: 0, fontSize: '1.2rem', fontWeight: 700, color: '#111827' },
  modalSub: { color: '#6b7280', fontSize: '0.85rem', margin: '0.5rem 0 1rem' },
  formGroup: { marginBottom: '1rem' },
  input: { width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '0.9rem', boxSizing: 'border-box' },
  msg: { fontSize: '0.82rem', fontWeight: 600, margin: '0.5rem 0' },
  btnRow: { display: 'flex', gap: '0.75rem', marginTop: '1rem' },
  cancelBtn: { flex: 1, padding: '8px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', color: '#374151', cursor: 'pointer', fontWeight: 600 },
  submitBtn: { flex: 1, padding: '8px', border: 'none', borderRadius: 8, background: '#7c3aed', color: '#fff', cursor: 'pointer', fontWeight: 600 },
};
