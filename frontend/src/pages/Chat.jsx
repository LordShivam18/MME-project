import { useState, useEffect, useRef } from 'react';
import axiosClient from '../api/axiosClient';

function timeAgo(dateStr) {
  const now = new Date();
  const d = new Date(dateStr);
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function Chat() {
  const [conversations, setConversations] = useState([]);
  const [activeConvo, setActiveConvo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMsg, setNewMsg] = useState('');
  const [contacts, setContacts] = useState([]);
  const [showNewChat, setShowNewChat] = useState(false);
  const [currentUserId, setCurrentUserId] = useState(null);
  const messagesEndRef = useRef(null);
  const isTabFocused = useRef(true);

  // Track tab focus for polling debounce
  useEffect(() => {
    const onFocus = () => { isTabFocused.current = true; };
    const onBlur = () => { isTabFocused.current = false; };
    window.addEventListener('focus', onFocus);
    window.addEventListener('blur', onBlur);
    return () => { window.removeEventListener('focus', onFocus); window.removeEventListener('blur', onBlur); };
  }, []);

  // Fetch current user
  useEffect(() => {
    axiosClient.get('/api/v1/me').then(res => {
      setCurrentUserId(res.data?.user?.user_id || res.data?.user?.id);
    }).catch(() => {});
  }, []);

  // Fetch conversations
  const fetchConversations = async () => {
    try {
      const res = await axiosClient.get('/api/v1/conversations');
      setConversations(res.data);
    } catch (e) { /* silent */ }
  };

  // Fetch messages for active conversation
  const fetchMessages = async () => {
    if (!activeConvo) return;
    try {
      const res = await axiosClient.get(`/api/v1/messages/${activeConvo.id}`);
      setMessages(res.data);
      // Mark as read
      await axiosClient.patch(`/api/v1/messages/${activeConvo.id}/read`);
    } catch (e) { /* silent */ }
  };

  // Fetch contacts for new conversation
  const fetchContacts = async () => {
    try {
      const res = await axiosClient.get('/api/v1/contacts');
      setContacts(res.data);
    } catch (e) { /* silent */ }
  };

  useEffect(() => {
    fetchConversations();
    fetchContacts();
  }, []);

  // Poll conversations every 10s
  useEffect(() => {
    const interval = setInterval(() => {
      if (isTabFocused.current) fetchConversations();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  // Poll messages every 5s when a conversation is active
  useEffect(() => {
    fetchMessages();
    const interval = setInterval(() => {
      if (isTabFocused.current && activeConvo) fetchMessages();
    }, 5000);
    return () => clearInterval(interval);
  }, [activeConvo]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!newMsg.trim() || !activeConvo) return;
    try {
      await axiosClient.post('/api/v1/messages', {
        conversation_id: activeConvo.id,
        content: newMsg.trim()
      });
      setNewMsg('');
      fetchMessages();
      fetchConversations();
    } catch (e) {
      alert('Failed to send message');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const startConversation = async (contactId) => {
    try {
      const res = await axiosClient.post('/api/v1/conversations', { contact_id: contactId });
      setShowNewChat(false);
      fetchConversations();
      // Set active
      setActiveConvo({ id: res.data.id, contact_name: res.data.contact_name });
    } catch (e) {
      alert('Failed to start conversation');
    }
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 120px)', fontFamily: 'sans-serif', gap: 0 }}>
      {/* Left: Conversation List */}
      <div style={{ width: '300px', minWidth: '300px', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', background: '#fff' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#0f172a' }}>💬 Messages</h3>
          <button onClick={() => setShowNewChat(!showNewChat)} style={{ background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '6px', padding: '0.3rem 0.6rem', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600 }}>+ New</button>
        </div>

        {showNewChat && (
          <div style={{ padding: '0.75rem', borderBottom: '1px solid #e2e8f0', background: '#f8fafc', maxHeight: '200px', overflowY: 'auto' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '0.5rem', fontWeight: 600 }}>SELECT CONTACT</div>
            {contacts.map(c => (
              <div key={c.id} onClick={() => startConversation(c.id)} style={{ padding: '0.4rem 0.5rem', cursor: 'pointer', borderRadius: '4px', fontSize: '0.85rem', color: '#334155' }}
                onMouseEnter={e => e.target.style.background = '#e2e8f0'}
                onMouseLeave={e => e.target.style.background = 'transparent'}
              >
                {c.name} <span style={{ color: '#94a3b8', fontSize: '0.75rem' }}>({c.type})</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.9rem' }}>No conversations yet</div>
          ) : (
            conversations.map(c => (
              <div key={c.id} onClick={() => setActiveConvo(c)} style={{
                padding: '0.75rem 1rem', cursor: 'pointer', borderBottom: '1px solid #f1f5f9',
                background: activeConvo?.id === c.id ? '#eff6ff' : '#fff',
                borderLeft: activeConvo?.id === c.id ? '3px solid #3b82f6' : '3px solid transparent',
                transition: 'all 0.1s ease'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>{c.contact_name}</strong>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    {c.unread_count > 0 && (
                      <span style={{ background: '#3b82f6', color: '#fff', borderRadius: '10px', padding: '1px 7px', fontSize: '0.7rem', fontWeight: 700 }}>{c.unread_count}</span>
                    )}
                    <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{timeAgo(c.last_message_at)}</span>
                  </div>
                </div>
                {c.last_message_preview && (
                  <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.25rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.last_message_preview}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: Message Thread */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#f8fafc' }}>
        {!activeConvo ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>💬</div>
              <h2 style={{ margin: 0, color: '#64748b' }}>Select a conversation</h2>
              <p style={{ color: '#94a3b8' }}>or start a new one</p>
            </div>
          </div>
        ) : (
          <>
            {/* Header */}
            <div style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid #e2e8f0', background: '#fff', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: '#3b82f6', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.9rem' }}>
                {activeConvo.contact_name?.[0]?.toUpperCase() || '?'}
              </div>
              <div>
                <strong style={{ color: '#0f172a' }}>{activeConvo.contact_name}</strong>
              </div>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#94a3b8', marginTop: '2rem' }}>No messages yet. Say hello! 👋</div>
              )}
              {messages.map(m => {
                const isMine = m.sender_user_id === currentUserId;
                return (
                  <div key={m.id} style={{ display: 'flex', justifyContent: isMine ? 'flex-end' : 'flex-start' }}>
                    <div style={{
                      maxWidth: '65%', padding: '0.6rem 1rem', borderRadius: '12px',
                      background: isMine ? '#3b82f6' : '#fff',
                      color: isMine ? '#fff' : '#0f172a',
                      border: isMine ? 'none' : '1px solid #e2e8f0',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                    }}>
                      <div style={{ fontSize: '0.875rem', lineHeight: '1.4', wordBreak: 'break-word' }}>{m.content}</div>
                      <div style={{ fontSize: '0.65rem', marginTop: '0.3rem', opacity: 0.7, textAlign: 'right' }}>
                        {timeAgo(m.created_at)}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div style={{ padding: '0.75rem 1.5rem', borderTop: '1px solid #e2e8f0', background: '#fff', display: 'flex', gap: '0.75rem' }}>
              <input
                type="text"
                value={newMsg}
                onChange={e => setNewMsg(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a message..."
                style={{ flex: 1, padding: '0.6rem 1rem', border: '1px solid #d1d5db', borderRadius: '8px', fontSize: '0.9rem', outline: 'none' }}
                maxLength={2048}
              />
              <button onClick={handleSend} disabled={!newMsg.trim()} style={{
                padding: '0.6rem 1.2rem', background: newMsg.trim() ? '#3b82f6' : '#94a3b8',
                color: '#fff', border: 'none', borderRadius: '8px', cursor: newMsg.trim() ? 'pointer' : 'default',
                fontWeight: 600, fontSize: '0.9rem', transition: 'background 0.15s'
              }}>
                Send
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
