import React, { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { useNavigate } from 'react-router-dom';

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [stats, setStats] = useState({ 
    total_users: 0, 
    total_organizations: 0, 
    total_products: 0,
    active_users_last_7_days: 0,
    average_ai_accuracy: 0,
    top_5_organizations: [],
    low_performing_orgs: []
  });

  useEffect(() => {
    const verifyAdmin = async () => {
      try {
        const meRes = await axiosClient.get('/api/v1/me');
        if (meRes.data && meRes.data.user && meRes.data.user.is_platform_admin) {
          setIsAdmin(true);
          const statsRes = await axiosClient.get('/api/v1/admin/stats');
          setStats(statsRes.data);
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ background: '#eff6ff', padding: '1.5rem', borderRadius: '8px', border: '1px solid #bfdbfe' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#1e40af', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>🏢 Organizations</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: '#1d4ed8' }}>{stats.total_organizations}</p>
        </div>
        <div style={{ background: '#f0fdf4', padding: '1.5rem', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#166534', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>👥 Active Users (7d)</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: '#15803d' }}>{stats.active_users_last_7_days} <span style={{fontSize: '1rem', color: '#6b7280', fontWeight: 'normal'}}>/ {stats.total_users} total</span></p>
        </div>
        <div style={{ background: '#fffbeb', padding: '1.5rem', borderRadius: '8px', border: '1px solid #fde68a' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#92400e', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>📦 Tracked Products</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: '#b45309' }}>{stats.total_products}</p>
        </div>
        <div style={{ background: stats.average_ai_accuracy >= 80 ? '#f0fdf4' : '#fef2f2', padding: '1.5rem', borderRadius: '8px', border: `1px solid ${stats.average_ai_accuracy >= 80 ? '#bbf7d0' : '#fecaca'}` }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: stats.average_ai_accuracy >= 80 ? '#166534' : '#991b1b', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>🤖 AI Accuracy</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0, color: stats.average_ai_accuracy >= 80 ? '#15803d' : '#b91c1c' }}>{stats.average_ai_accuracy}%</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', padding: '1.5rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', color: '#374151' }}>🚀 Top Organizations (by Activity)</h3>
          {stats.top_5_organizations.length > 0 ? (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {stats.top_5_organizations.map((org, i) => (
                <li key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid #f3f4f6' }}>
                  <span>{org.name}</span>
                  <span style={{ fontWeight: 'bold', color: '#10b981' }}>{org.metric} sales</span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: '#6b7280' }}>No data available.</p>
          )}
        </div>

        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', padding: '1.5rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', color: '#374151' }}>⚠️ High Error Organizations</h3>
          {stats.low_performing_orgs.length > 0 ? (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {stats.low_performing_orgs.map((org, i) => (
                <li key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid #f3f4f6' }}>
                  <span>{org.name}</span>
                  <span style={{ fontWeight: 'bold', color: '#ef4444' }}>{org.metric}% error rate</span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: '#6b7280' }}>All organizations are performing well!</p>
          )}
        </div>
      </div>
    </div>
  );
}
