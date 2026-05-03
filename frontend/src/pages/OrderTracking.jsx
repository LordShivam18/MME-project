import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

const STATUS_STEPS = ['placed', 'confirmed', 'packed', 'shipped', 'delivered'];
const STATUS_COLORS = {
  placed: '#6366f1',
  confirmed: '#3b82f6',
  packed: '#f59e0b',
  shipped: '#10b981',
  delivered: '#059669',
  cancelled: '#ef4444',
  returned: '#f97316',
};

export default function OrderTracking() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [timeline, setTimeline] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchTimeline();
  }, [orderId]);

  const fetchTimeline = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get(`/api/v1/orders/${orderId}/timeline`);
      setTimeline(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load order tracking');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) return <div style={{ padding: '2rem' }}><LoadingSpinner /></div>;
  if (error) return <div style={{ padding: '2rem' }}><ErrorState message={error} /></div>;
  if (!timeline) return null;

  const currentStatus = timeline.status;
  const isCancelled = currentStatus === 'cancelled';
  const isReturned = currentStatus === 'returned';
  const currentIdx = STATUS_STEPS.indexOf(currentStatus);
  const completedSteps = timeline.timeline?.map(t => t.step) || [];

  return (
    <div style={s.page}>
      <button onClick={() => navigate(-1)} style={s.backBtn}>← Back</button>
      
      <div style={s.header}>
        <h1 style={s.title}>Order #{timeline.order_id}</h1>
        <span style={{
          ...s.statusBadge,
          backgroundColor: (STATUS_COLORS[currentStatus] || '#94a3b8') + '18',
          color: STATUS_COLORS[currentStatus] || '#94a3b8',
          borderColor: STATUS_COLORS[currentStatus] || '#94a3b8',
        }}>
          {currentStatus?.toUpperCase()}
        </span>
      </div>

      {/* Progress Bar */}
      {!isCancelled && !isReturned && (
        <div style={s.progressWrap}>
          {STATUS_STEPS.map((step, i) => {
            const isCompleted = completedSteps.includes(step);
            const isCurrent = step === currentStatus;
            return (
              <div key={step} style={s.progressStep}>
                <div style={{
                  ...s.dot,
                  backgroundColor: isCompleted || isCurrent ? (STATUS_COLORS[step] || '#3b82f6') : '#e2e8f0',
                  boxShadow: isCurrent ? `0 0 0 4px ${(STATUS_COLORS[step] || '#3b82f6')}30` : 'none',
                }}>
                  {isCompleted ? '✓' : (i + 1)}
                </div>
                {i < STATUS_STEPS.length - 1 && (
                  <div style={{
                    ...s.connector,
                    backgroundColor: isCompleted && completedSteps.includes(STATUS_STEPS[i + 1]) ? '#10b981' : '#e2e8f0',
                  }} />
                )}
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: isCurrent ? '#0f172a' : '#94a3b8', marginTop: '0.5rem', textTransform: 'capitalize' }}>
                  {step}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {(isCancelled || isReturned) && (
        <div style={{
          padding: '1.5rem', borderRadius: '12px', border: '1px solid',
          borderColor: isCancelled ? '#fecaca' : '#fed7aa',
          backgroundColor: isCancelled ? '#fef2f2' : '#fff7ed',
          color: isCancelled ? '#991b1b' : '#9a3412',
          marginBottom: '1.5rem', fontWeight: 600,
        }}>
          {isCancelled ? '❌ This order was cancelled.' : '🔄 This order was returned.'}
        </div>
      )}

      {/* Timeline Detail */}
      <div style={s.timelineCard}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#0f172a', margin: '0 0 1.25rem 0' }}>Status Timeline</h2>
        <div>
          {timeline.timeline?.map((entry, i) => (
            <div key={i} style={s.timelineEntry}>
              <div style={{
                ...s.timelineDot,
                backgroundColor: STATUS_COLORS[entry.step] || '#94a3b8',
              }} />
              {i < timeline.timeline.length - 1 && <div style={s.timelineLine} />}
              <div style={s.timelineContent}>
                <strong style={{ textTransform: 'capitalize', color: '#1e293b' }}>{entry.step}</strong>
                <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                  {entry.time ? new Date(entry.time).toLocaleString() : '—'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const s = {
  page: { fontFamily: '"Inter", sans-serif', maxWidth: '700px', margin: '0 auto', padding: '1.5rem' },
  backBtn: { background: 'none', border: 'none', color: '#3b82f6', fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem', padding: 0, marginBottom: '1.5rem' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' },
  title: { fontSize: '1.5rem', fontWeight: 800, color: '#0f172a', margin: 0 },
  statusBadge: { padding: '4px 14px', borderRadius: '8px', fontSize: '0.8rem', fontWeight: 700, border: '1px solid' },
  progressWrap: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '2.5rem', position: 'relative' },
  progressStep: { display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', flex: 1 },
  dot: { width: '32px', height: '32px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.75rem', color: '#fff', transition: 'all 0.3s', zIndex: 1 },
  connector: { position: 'absolute', top: '15px', left: '50%', width: '100%', height: '3px', transition: 'background 0.3s' },
  timelineCard: { backgroundColor: '#fff', borderRadius: '12px', padding: '1.5rem', border: '1px solid #e2e8f0' },
  timelineEntry: { display: 'flex', alignItems: 'flex-start', gap: '1rem', position: 'relative', paddingBottom: '1.25rem' },
  timelineDot: { width: '12px', height: '12px', borderRadius: '50%', flexShrink: 0, marginTop: '4px' },
  timelineLine: { position: 'absolute', left: '5px', top: '18px', width: '2px', height: 'calc(100% - 16px)', backgroundColor: '#e2e8f0' },
  timelineContent: { display: 'flex', flexDirection: 'column', gap: '2px' },
};
