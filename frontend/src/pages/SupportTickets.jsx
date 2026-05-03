import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

const STATUS_COLORS = { open: '#eab308', in_progress: '#3b82f6', resolved: '#10b981' };
const PRIORITY_COLORS = { low: '#64748b', medium: '#f59e0b', high: '#ef4444' };

export default function SupportTickets() {
  const [tickets, setTickets] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchTickets();
  }, []);

  const fetchTickets = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get('/api/v1/tickets');
      setTickets(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load support tickets');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) return <div style={{ padding: '2rem' }}><LoadingSpinner /></div>;
  if (error) return <div style={{ padding: '2rem' }}><ErrorState message={error} /></div>;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <h1 style={s.title}>🎫 Support Tickets</h1>
        <p style={s.subtitle}>Manage your customer support requests</p>
      </div>

      {tickets.length === 0 ? (
        <div style={s.empty}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>✅</div>
          <h3 style={{ color: '#64748b', margin: '0 0 0.5rem 0' }}>No active tickets</h3>
          <p style={{ color: '#94a3b8', margin: 0 }}>You're all caught up!</p>
        </div>
      ) : (
        <div style={s.grid}>
          {tickets.map(ticket => (
            <div key={ticket.id} style={s.card} onClick={() => navigate(`/tickets/${ticket.id}`)}>
              <div style={s.cardHeader}>
                <div>
                  <span style={{ fontWeight: 800, color: '#0f172a' }}>Ticket #{ticket.id}</span>
                  <span style={{ color: '#64748b', fontSize: '0.8rem', marginLeft: '0.5rem' }}>Order #{ticket.order_id}</span>
                </div>
                <span style={{ ...s.badge, backgroundColor: STATUS_COLORS[ticket.status] + '20', color: STATUS_COLORS[ticket.status] }}>
                  {ticket.status.replace('_', ' ').toUpperCase()}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.9rem', color: '#334155', textTransform: 'capitalize' }}>
                  {ticket.issue_type.replace('_', ' ')}
                </span>
                <span style={{ ...s.priorityBadge, color: PRIORITY_COLORS[ticket.priority] }}>
                  {ticket.priority.toUpperCase()} PRIORITY
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const s = {
  page: { padding: '2rem', maxWidth: '1000px', margin: '0 auto' },
  header: { marginBottom: '2rem' },
  title: { fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', margin: '0 0 0.5rem 0' },
  subtitle: { color: '#64748b', fontSize: '1rem', margin: 0 },
  empty: { textAlign: 'center', padding: '4rem 2rem', backgroundColor: '#fff', borderRadius: '12px', border: '1px dashed #cbd5e1' },
  grid: { display: 'flex', flexDirection: 'column', gap: '1rem' },
  card: { backgroundColor: '#fff', borderRadius: '12px', padding: '1.25rem 1.5rem', border: '1px solid #e2e8f0', cursor: 'pointer', transition: 'box-shadow 0.2s, border-color 0.2s' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' },
  badge: { padding: '4px 10px', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.05em' },
  priorityBadge: { fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.05em' }
};
