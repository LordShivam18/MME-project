import React, { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { useNavigate } from 'react-router-dom';

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [stats, setStats] = useState({ users: 0, organizations: 0, products: 0 });

  useEffect(() => {
    const verifyAdmin = async () => {
      try {
        const meRes = await axiosClient.get('/api/v1/me');
        if (meRes.data && meRes.data.user && meRes.data.user.is_platform_admin) {
          setIsAdmin(true);
          // Here we would typically fetch platform-wide stats
          // For now, using mock stats for the placeholder
          setStats({ users: 15, organizations: 5, products: 1240 });
        } else {
          navigate('/dashboard'); // Kick out non-admins
        }
      } catch (err) {
        navigate('/login');
      } finally {
        setLoading(false);
      }
    };
    verifyAdmin();
  }, [navigate]);

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading Admin Portal...</div>;
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ color: '#1e3a8a', margin: 0 }}>Platform Administration</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button 
            onClick={() => navigate('/dashboard')}
            style={{ padding: '0.5rem 1rem', background: '#e5e7eb', color: '#374151', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Enter Demo Organization
          </button>
          <button 
            onClick={() => {
              localStorage.removeItem('access_token');
              localStorage.removeItem('refresh_token');
              navigate('/login');
            }}
            style={{ padding: '0.5rem 1rem', background: '#ef4444', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Logout
          </button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ background: '#eff6ff', padding: '1.5rem', borderRadius: '8px', border: '1px solid #bfdbfe' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#1e40af' }}>Organizations</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: '#1d4ed8' }}>{stats.organizations}</p>
        </div>
        <div style={{ background: '#f0fdf4', padding: '1.5rem', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#166534' }}>Active Users</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: '#15803d' }}>{stats.users}</p>
        </div>
        <div style={{ background: '#fef2f2', padding: '1.5rem', borderRadius: '8px', border: '1px solid #fecaca' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#991b1b' }}>Total Products Tracked</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: '#b91c1c' }}>{stats.products}</p>
        </div>
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', padding: '2rem', textAlign: 'center', color: '#6b7280' }}>
        <h2>Admin Management Features</h2>
        <p>Tenant management, billing overviews, and global settings will go here.</p>
      </div>
    </div>
  );
}
