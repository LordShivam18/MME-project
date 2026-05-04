import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { useAuth } from '../context/AuthContext';
import { isCustomer, isSeller, isAdmin } from '../utils/roles';
import './Layout.css';

const navItems = [
  { section: 'Core' },
  { to: '/dashboard',  icon: '📊', label: 'Dashboard' },
  { to: '/products',   icon: '📦', label: 'Products' },
  { to: '/inventory',  icon: '🏭', label: 'Inventory' },
  { section: 'Business' },
  { to: '/contacts',   icon: '🤝', label: 'CRM & Orders' },
  { to: '/marketplace', icon: '🏪', label: 'Marketplace' },
  { to: '/search',     icon: '🔍', label: 'Product Search' },
  { to: '/seller-dashboard', icon: '🤖', label: 'AI Negotiations' },
  { to: '/chat',       icon: '💬', label: 'Messages' },
  { to: '/tickets',    icon: '🎫', label: 'Support Tickets' },
  { to: '/profit',     icon: '💰', label: 'Profit Analytics' },
  { section: 'System' },
  { to: '/billing',    icon: '💳', label: 'Billing' },
  { to: '/settings',   icon: '⚙️', label: 'Settings' },
];

const priorityColors = {
  high:   { bg: '#fef2f2', border: '#fecaca', text: '#991b1b', dot: '#ef4444' },
  medium: { bg: '#fffbeb', border: '#fde68a', text: '#92400e', dot: '#f59e0b' },
  low:    { bg: '#ffffff', border: '#e5e7eb', text: '#374151', dot: '#6b7280' },
};

const typeIcons = {
  low_stock: '📉',
  ai_alert: '🤖',
  order_update: '🚚',
  negotiation: '💰',
  payment: '💳',
  insight: '⚡',
  system: 'ℹ️',
};

export default function Layout({ children }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [notifications, setNotifications] = useState([]);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const unreadCount = notifications.filter(n => !n.is_read).length;

  const fetchNotifications = async () => {
    try {
      const res = await axiosClient.get('/api/v1/notifications');
      setNotifications(res.data);
    } catch (err) {
      // silent
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 15000); // 15s polling
    return () => clearInterval(interval);
  }, []);

  const handleMarkRead = async (id) => {
    try {
      await axiosClient.patch(`/api/v1/notifications/${id}/read`, { is_read: true });
      fetchNotifications();
    } catch (err) {
      console.error(err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await axiosClient.patch('/api/v1/notifications/read-all');
      fetchNotifications();
    } catch (err) {
      console.error(err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <span className="sidebar-logo">📦</span>
          <span className="sidebar-title">NME IMS</span>
        </div>

        <nav className="sidebar-nav">
          
          {navItems.filter(item => {
            if (!user) return true;
            if (isCustomer(user)) {
              const allowed = ['/dashboard', '/marketplace', '/search', '/contacts', '/tickets', '/profit', '/billing', '/settings'];
              if (item.to && !allowed.includes(item.to)) return false;
            }
            if (isSeller(user)) {
              const allowed = ['/dashboard', '/products', '/inventory', '/contacts', '/seller-dashboard', '/tickets', '/profit', '/chat', '/billing', '/settings', '/marketplace'];
              if (item.to && !allowed.includes(item.to)) return false;
            }
            return true;
          }).map((item, i) => {
            let label = item.label;
            if (isCustomer(user) && item.to === '/contacts') label = 'Orders & Sellers';
            if (isCustomer(user) && item.to === '/profit') label = 'Savings Dashboard';
            if (isSeller(user) && item.to === '/contacts') label = 'CRM & Orders';
            if (isSeller(user) && item.to === '/profit') label = 'Profit Analytics';

            if (item.section) {
              return <div key={i} className="sidebar-section-label">{item.section}</div>;
            }
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <span className="sidebar-link-icon">{item.icon}</span>
                {label}
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button className="sidebar-logout-btn" onClick={handleLogout}>
            <span className="sidebar-link-icon">🚪</span>
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="main-content">
        <div className="main-topbar">
          {/* Notification Bell */}
          <div style={{ position: 'relative', cursor: 'pointer' }} onClick={() => setIsDropdownOpen(!isDropdownOpen)}>
            <span style={{ fontSize: '1.5rem' }}>🔔</span>
            {unreadCount > 0 && (
              <div style={{
                position: 'absolute', top: '-5px', right: '-5px',
                backgroundColor: '#ef4444', color: 'white',
                fontSize: '0.7rem', fontWeight: 'bold',
                borderRadius: '50%', width: '18px', height: '18px',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>
                {unreadCount}
              </div>
            )}
          </div>

          {isDropdownOpen && (
            <div style={{
              position: 'absolute', top: '50px', right: '1.5rem',
              width: '360px', backgroundColor: 'white',
              borderRadius: '12px', boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
              zIndex: 1000, maxHeight: '480px', overflowY: 'auto',
              border: '1px solid #e5e7eb'
            }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#f9fafb', borderRadius: '12px 12px 0 0' }}>
                <strong>Notifications</strong>
                {unreadCount > 0 && (
                  <button onClick={handleMarkAllRead} style={{ background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600 }}>
                    Mark all read
                  </button>
                )}
              </div>
              {notifications.length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#6b7280' }}>No notifications yet</div>
              ) : (
                notifications.slice(0, 20).map(n => {
                  const colors = priorityColors[n.priority] || priorityColors.low;
                  const icon = typeIcons[n.type] || '🔔';
                  return (
                    <div key={n.id} style={{
                      padding: '0.75rem 1rem', 
                      borderBottom: '1px solid #f3f4f6',
                      backgroundColor: n.is_read ? '#fff' : colors.bg,
                      cursor: n.is_read ? 'default' : 'pointer',
                      borderLeft: n.is_read ? '3px solid transparent' : `3px solid ${colors.dot}`,
                      transition: 'background 0.15s ease'
                    }} onClick={() => !n.is_read && handleMarkRead(n.id)}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                        <span style={{ fontSize: '1.1rem', flexShrink: 0 }}>{icon}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: '0.875rem', color: colors.text, fontWeight: n.is_read ? 400 : 600 }}>
                            {n.message}
                          </div>
                          <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginTop: '0.25rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            {new Date(n.created_at).toLocaleString()}
                            <span style={{ 
                              padding: '1px 6px', 
                              borderRadius: '4px', 
                              fontSize: '0.65rem', 
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              backgroundColor: colors.bg, 
                              color: colors.dot,
                              border: `1px solid ${colors.border}`
                            }}>
                              {n.priority}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        <div className="main-page-content">
          {children}
        </div>
      </div>
    </div>
  );
}
