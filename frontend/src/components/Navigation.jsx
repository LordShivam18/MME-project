import { useNavigate, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

export default function Navigation() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  
  const unreadCount = notifications.filter(n => !n.is_read).length;

  const fetchNotifications = async () => {
    try {
      const res = await axiosClient.get('/api/v1/notifications');
      setNotifications(res.data);
    } catch (err) {
      console.error("Failed to fetch notifications");
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000); // 60s polling
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
    localStorage.removeItem('token');
    // Using window.location.href ensures a complete hard-reset of the App.jsx Auth Context wrapper
    window.location.href = '/login'; 
  };

  return (
    <nav style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', borderBottom: '1px solid #eee', marginBottom: '2rem', backgroundColor: '#fafafa' }}>
       <div style={{ display: 'flex', gap: '2rem', fontWeight: 'bold' }}>
         <Link to="/dashboard" style={{ textDecoration: 'none', color: '#333' }}>Dashboard</Link>
         <Link to="/products" style={{ textDecoration: 'none', color: '#333' }}>Manage Products</Link>
         <Link to="/contacts" style={{ textDecoration: 'none', color: '#333' }}>CRM & Orders</Link>
         <Link to="/inventory" style={{ textDecoration: 'none', color: '#333' }}>Inventory Intelligence</Link>
         <Link to="/billing" style={{ textDecoration: 'none', color: '#333' }}>Billing</Link>
       </div>
       
       <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', position: 'relative' }}>
         {/* Notification Bell */}
         <div 
           style={{ position: 'relative', cursor: 'pointer' }}
           onClick={() => setIsDropdownOpen(!isDropdownOpen)}
         >
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

         {/* Dropdown */}
         {isDropdownOpen && (
           <div style={{
             position: 'absolute', top: '40px', right: '100px',
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
         
         <button onClick={handleLogout} style={{ padding: '0.25rem 1rem', background: '#dc3545', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
           Logout
         </button>
       </div>
    </nav>
  );
}
