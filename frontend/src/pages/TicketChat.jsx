import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

const STATUS_COLORS = { open: '#eab308', in_progress: '#3b82f6', resolved: '#10b981' };
const PRIORITY_COLORS = { low: '#64748b', medium: '#f59e0b', high: '#ef4444' };

export default function TicketChat() {
  const { ticketId } = useParams();
  const navigate = useNavigate();
  
  const [ticket, setTicket] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchTicket();
    fetchUser();
  }, [ticketId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [ticket?.messages]);

  const fetchUser = async () => {
    try {
      const res = await axiosClient.get('/api/v1/me');
      setCurrentUser(res.data.user);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchTicket = async () => {
    setLoading(true);
    try {
      const res = await axiosClient.get(`/api/v1/tickets/${ticketId}`);
      setTicket(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load ticket');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    setSending(true);
    try {
      const res = await axiosClient.post(`/api/v1/tickets/${ticketId}/message`, { message: message.trim() });
      setTicket(prev => ({
        ...prev,
        messages: [...prev.messages, res.data]
      }));
      setMessage('');
    } catch (err) {
      alert('Failed to send message: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSending(false);
    }
  };

  const handleStatusChange = async (newStatus) => {
    try {
      const res = await axiosClient.patch(`/api/v1/tickets/${ticketId}/status`, { status: newStatus });
      setTicket(res.data);
    } catch (err) {
      alert('Failed to update status: ' + (err.response?.data?.detail || err.message));
    }
  };

  if (loading) return <div style={{ padding: '2rem' }}><LoadingSpinner /></div>;
  if (error) return <div style={{ padding: '2rem' }}><ErrorState message={error} /></div>;
  if (!ticket) return null;

  const isSeller = currentUser?.business_type !== 'customer';

  return (
    <div style={s.page}>
      <button onClick={() => navigate(-1)} style={s.backBtn}>← Back</button>

      <div style={s.chatContainer}>
        {/* Header */}
        <div style={s.header}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <h2 style={{ margin: 0, color: '#0f172a', fontSize: '1.25rem' }}>Support Ticket #{ticket.id}</h2>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 500 }}>Order #{ticket.order_id}</span>
              <span style={{ fontSize: '0.85rem', color: '#64748b' }}>•</span>
              <span style={{ fontSize: '0.85rem', color: '#64748b', textTransform: 'capitalize' }}>Issue: {ticket.issue_type.replace('_', ' ')}</span>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ ...s.badge, backgroundColor: PRIORITY_COLORS[ticket.priority] + '20', color: PRIORITY_COLORS[ticket.priority] }}>
              {ticket.priority.toUpperCase()} PRIORITY
            </span>

            {isSeller ? (
              <select 
                value={ticket.status} 
                onChange={(e) => handleStatusChange(e.target.value)}
                style={{ ...s.statusSelect, borderColor: STATUS_COLORS[ticket.status], color: STATUS_COLORS[ticket.status] }}
              >
                <option value="open">OPEN</option>
                <option value="in_progress">IN PROGRESS</option>
                <option value="resolved">RESOLVED</option>
              </select>
            ) : (
              <span style={{ ...s.badge, backgroundColor: STATUS_COLORS[ticket.status] + '20', color: STATUS_COLORS[ticket.status] }}>
                {ticket.status.replace('_', ' ').toUpperCase()}
              </span>
            )}
          </div>
        </div>

        {/* Message List */}
        <div style={s.messageArea}>
          {ticket.events.map((event) => (
             <div key={`event-${event.id}`} style={s.eventRow}>
               <span style={s.eventBubble}>
                 Status changed to <strong>{event.new_status.replace('_', ' ')}</strong> at {new Date(event.created_at).toLocaleTimeString()}
               </span>
             </div>
          ))}

          {ticket.messages.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#94a3b8', padding: '2rem 0' }}>
              Describe your issue below to start the conversation.
            </div>
          ) : (
            ticket.messages.map((msg) => {
              const isMine = msg.sender_id === currentUser?.id;
              return (
                <div key={`msg-${msg.id}`} style={{ ...s.msgRow, justifyContent: isMine ? 'flex-end' : 'flex-start' }}>
                  <div style={{ ...s.msgBubble, backgroundColor: isMine ? '#3b82f6' : '#f1f5f9', color: isMine ? '#fff' : '#0f172a' }}>
                    <div style={s.msgText}>{msg.message}</div>
                    <div style={{ ...s.msgTime, color: isMine ? '#bfdbfe' : '#94a3b8' }}>
                      {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div style={s.inputArea}>
          {ticket.status === 'resolved' ? (
            <div style={{ textAlign: 'center', color: '#64748b', padding: '0.5rem', fontWeight: 500 }}>
              This ticket has been resolved and is closed to new messages.
            </div>
          ) : (
            <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                type="text"
                placeholder="Type your message..."
                value={message}
                onChange={e => setMessage(e.target.value)}
                style={s.input}
                disabled={sending}
              />
              <button type="submit" style={s.sendBtn} disabled={sending || !message.trim()}>
                {sending ? '...' : 'Send'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

const s = {
  page: { maxWidth: '800px', margin: '0 auto', padding: '1.5rem', height: 'calc(100vh - 100px)', display: 'flex', flexDirection: 'column' },
  backBtn: { background: 'none', border: 'none', color: '#3b82f6', fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem', padding: 0, marginBottom: '1rem', alignSelf: 'flex-start' },
  chatContainer: { flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' },
  header: { padding: '1.25rem 1.5rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#f8fafc' },
  badge: { padding: '4px 10px', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.05em' },
  statusSelect: { padding: '4px 8px', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 700, border: '2px solid', outline: 'none', cursor: 'pointer', backgroundColor: 'transparent' },
  messageArea: { flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem', backgroundColor: '#fff' },
  msgRow: { display: 'flex', width: '100%' },
  msgBubble: { maxWidth: '75%', padding: '0.75rem 1rem', borderRadius: '12px', position: 'relative' },
  msgText: { fontSize: '0.95rem', lineHeight: '1.4' },
  msgTime: { fontSize: '0.7rem', marginTop: '4px', textAlign: 'right' },
  eventRow: { display: 'flex', justifyContent: 'center', margin: '0.5rem 0' },
  eventBubble: { backgroundColor: '#f1f5f9', color: '#64748b', fontSize: '0.75rem', padding: '4px 12px', borderRadius: '16px' },
  inputArea: { padding: '1.25rem 1.5rem', borderTop: '1px solid #e2e8f0', backgroundColor: '#f8fafc' },
  input: { flex: 1, padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '0.95rem', outline: 'none' },
  sendBtn: { backgroundColor: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px', padding: '0 1.5rem', fontWeight: 600, cursor: 'pointer', transition: 'background 0.2s' },
};
