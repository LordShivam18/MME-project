import { useNavigate, Link } from 'react-router-dom';

export default function Navigation() {
  const navigate = useNavigate();
  
  const handleLogout = () => {
    localStorage.removeItem('token');
    // Using window.location.href ensures a complete hard-reset of the App.jsx Auth Context wrapper
    window.location.href = '/login'; 
  };

  return (
    <nav style={{ display: 'flex', justifyContent: 'space-between', padding: '1rem', borderBottom: '1px solid #eee', marginBottom: '2rem', backgroundColor: '#fafafa' }}>
       <div style={{ display: 'flex', gap: '2rem', fontWeight: 'bold' }}>
         <Link to="/dashboard" style={{ textDecoration: 'none', color: '#333' }}>Dashboard</Link>
         <Link to="/products" style={{ textDecoration: 'none', color: '#333' }}>Manage Products</Link>
         <Link to="/inventory" style={{ textDecoration: 'none', color: '#333' }}>Inventory Intelligence</Link>
       </div>
       <button onClick={handleLogout} style={{ padding: '0.25rem 1rem', background: '#dc3545', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
         Logout
       </button>
    </nav>
  );
}
