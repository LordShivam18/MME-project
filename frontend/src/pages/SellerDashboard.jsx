import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

const RISK_COLORS = {
  safe: { bg: '#d1fae5', color: '#065f46', icon: '✅' },
  moderate: { bg: '#fef3c7', color: '#92400e', icon: '⚠️' },
  risky: { bg: '#fee2e2', color: '#991b1b', icon: '🔴' },
};

export default function SellerDashboard() {
  const [requests, setRequests] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  useEffect(() => { fetchDashboard(); }, []);

  const fetchDashboard = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get('/api/v1/pricing/requests/dashboard');
      setRequests(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load dashboard');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (requestId, action) => {
    setActionLoading(requestId);
    try {
      await axiosClient.patch(`/api/v1/price-request/${requestId}`, {
        action,
        ...(action === 'accept' ? {} : { reason: 'Seller rejected' }),
      });
      setRequests(prev => prev.filter(r => r.request_id !== requestId));
    } catch (err) {
      alert(err.response?.data?.detail || 'Action failed');
    } finally {
      setActionLoading(null);
    }
  };

  if (isLoading) return <div style={{ padding: '2rem' }}><LoadingSpinner /></div>;
  if (error) return <div style={{ padding: '2rem' }}><ErrorState message={error} /></div>;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <div>
          <h1 style={s.title}>🤖 AI Negotiation Dashboard</h1>
          <p style={s.subtitle}>Pending pricing requests with AI-assisted insights</p>
        </div>
        <div style={s.statBadge}>{requests.length} pending</div>
      </div>

      {requests.length === 0 ? (
        <div style={s.empty}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🎯</div>
          <h3 style={{ color: '#64748b' }}>No pending requests</h3>
          <p style={{ color: '#94a3b8' }}>All negotiations are resolved</p>
        </div>
      ) : (
        <div style={s.grid}>
          {requests.map(req => {
            const risk = RISK_COLORS[req.risk_level] || RISK_COLORS.moderate;
            const marginPct = (req.margin_impact * 100).toFixed(1);
            const isLoss = req.margin_impact > 0;
            return (
              <div key={req.request_id} style={s.card}>
                <div style={s.cardTop}>
                  <div>
                    <h3 style={s.productName}>{req.product_name}</h3>
                    <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Qty: {req.quantity}</span>
                  </div>
                  <span style={{ ...s.riskBadge, backgroundColor: risk.bg, color: risk.color }}>
                    {risk.icon} {req.risk_level}
                  </span>
                </div>

                <div style={s.priceRow}>
                  <div style={s.priceBox}>
                    <div style={s.priceLabel}>Requested</div>
                    <div style={{ ...s.priceValue, color: '#ef4444' }}>₹{req.requested_price?.toFixed(2)}</div>
                  </div>
                  <div style={{ fontSize: '1.2rem', color: '#94a3b8', alignSelf: 'center' }}>vs</div>
                  <div style={s.priceBox}>
                    <div style={s.priceLabel}>Bulk Price</div>
                    <div style={{ ...s.priceValue, color: '#10b981' }}>₹{req.bulk_price?.toFixed(2)}</div>
                  </div>
                </div>

                <div style={s.metricsRow}>
                  <div style={s.metric}>
                    <span style={s.metricLabel}>Margin Impact</span>
                    <span style={{ fontWeight: 700, color: isLoss ? '#ef4444' : '#10b981' }}>
                      {isLoss ? '-' : '+'}{Math.abs(marginPct)}%
                    </span>
                  </div>
                  <div style={s.metric}>
                    <span style={s.metricLabel}>Demand</span>
                    <div style={s.demandBar}>
                      <div style={{ ...s.demandFill, width: `${Math.min(req.demand_score * 100, 100)}%` }} />
                    </div>
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{(req.demand_score * 100).toFixed(0)}%</span>
                  </div>
                </div>

                <div style={s.aiBox}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>🤖 AI:</span>
                  <span style={{ fontSize: '0.85rem', color: '#334155' }}>{req.ai_suggestion}</span>
                </div>

                <div style={s.actions}>
                  <button
                    onClick={() => handleAction(req.request_id, 'accept')}
                    disabled={actionLoading === req.request_id}
                    style={s.acceptBtn}
                  >
                    {actionLoading === req.request_id ? '...' : '✓ Accept'}
                  </button>
                  <button
                    onClick={() => handleAction(req.request_id, 'reject')}
                    disabled={actionLoading === req.request_id}
                    style={s.rejectBtn}
                  >
                    ✗ Reject
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const s = {
  page: { fontFamily: '"Inter", sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1.5rem' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' },
  title: { fontSize: '1.5rem', fontWeight: 800, color: '#0f172a', margin: 0 },
  subtitle: { color: '#64748b', margin: '0.25rem 0 0 0', fontSize: '0.9rem' },
  statBadge: { padding: '6px 14px', backgroundColor: '#eff6ff', color: '#3b82f6', borderRadius: '8px', fontWeight: 700, fontSize: '0.9rem' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' },
  card: { backgroundColor: '#fff', borderRadius: '12px', padding: '1.25rem', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' },
  productName: { margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#0f172a' },
  riskBadge: { padding: '3px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap' },
  priceRow: { display: 'flex', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '1rem' },
  priceBox: { flex: 1, padding: '0.75rem', backgroundColor: '#f8fafc', borderRadius: '8px', textAlign: 'center' },
  priceLabel: { fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, marginBottom: '0.25rem' },
  priceValue: { fontSize: '1.15rem', fontWeight: 700 },
  metricsRow: { display: 'flex', gap: '1rem', marginBottom: '0.75rem' },
  metric: { flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' },
  metricLabel: { fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 },
  demandBar: { height: '6px', backgroundColor: '#e5e7eb', borderRadius: '3px', overflow: 'hidden' },
  demandFill: { height: '100%', backgroundColor: '#3b82f6', borderRadius: '3px', transition: 'width 0.3s' },
  aiBox: { padding: '0.6rem 0.75rem', backgroundColor: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0', display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1rem' },
  actions: { display: 'flex', gap: '0.5rem' },
  acceptBtn: { flex: 1, padding: '0.6rem', backgroundColor: '#059669', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.9rem' },
  rejectBtn: { flex: 1, padding: '0.6rem', backgroundColor: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.9rem' },
  empty: { textAlign: 'center', padding: '4rem 2rem', backgroundColor: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' },
};
