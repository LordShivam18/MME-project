import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import './Layout.css';

const navItems = [
  { section: 'Core' },
  { to: '/dashboard',  icon: '📊', label: 'Dashboard' },
  { to: '/products',   icon: '📦', label: 'Products' },
  { to: '/inventory',  icon: '🏭', label: 'Inventory' },
  { section: 'Business' },
  { to: '/contacts',   icon: '🤝', label: 'CRM & Orders' },
  { to: '/profit',     icon: '💰', label: 'Profit Analytics' },
  { section: 'System' },
  { to: '/billing',    icon: '💳', label: 'Billing' },
  { to: '/settings',   icon: '⚙️', label: 'Settings' },
];

export default function Layout({ children }) {
  const navigate = useNavigate();
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
    const interval = setInterval(fetchNotifications, 60000);
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
          {navItems.map((item, i) => {
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
                {item.label}
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
              width: '320px', backgroundColor: 'white',
              borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              zIndex: 1000, maxHeight: '400px', overflowY: 'auto',
              border: '1px solid #e5e7eb'
            }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e5e7eb', fontWeight: 'bold', backgroundColor: '#f9fafb' }}>
                Notifications
              </div>
              {notifications.length === 0 ? (
                <div style={{ padding: '1rem', textAlign: 'center', color: '#6b7280' }}>No notifications</div>
              ) : (
                notifications.map(n => (
                  <div key={n.id} style={{
                    padding: '1rem', borderBottom: '1px solid #f3f4f6',
                    backgroundColor: n.is_read ? 'white' : '#eff6ff',
                    cursor: 'pointer'
                  }} onClick={() => !n.is_read && handleMarkRead(n.id)}>
                    <div style={{ fontSize: '0.875rem', color: '#1f2937', marginBottom: '0.25rem' }}>
                      {n.message}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                      {new Date(n.created_at).toLocaleString()}
                      {n.type === 'insight' && <span style={{ marginLeft: '8px', color: '#8b5cf6', fontWeight: 'bold' }}>AI Insight</span>}
                      {n.type === 'low_stock' && <span style={{ marginLeft: '8px', color: '#ef4444', fontWeight: 'bold' }}>Low Stock</span>}
                    </div>
                  </div>
                ))
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
