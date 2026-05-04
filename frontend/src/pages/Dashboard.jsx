import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

export default function Dashboard() {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchMe = async () => {
      try {
        const res = await axiosClient.get('/api/v1/me');
        const userData = res.data?.user || null;
        console.log("USER:", userData);
        setUser(userData);
      } catch (err) {
        console.error(err);
        setUser(null);
        setError("Unable to load user session.");
      } finally {
        setIsLoading(false);
      }
    };
    fetchMe();
  }, []);

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>

      
      <div style={{ border: '2px dashed #ccc', padding: '3rem', borderRadius: '8px', textAlign: 'center', marginTop: '2rem', backgroundColor: '#f9f9f9' }}>
        <h2>System Dashboard</h2>
        <p style={{ color: '#666' }}>Secure backend authorization complete.</p>
        
        {isLoading && <LoadingSpinner />}
        {error && <ErrorState message={error} />}
        
        {user && (
          <div style={{ marginTop: '2rem', background: '#333', color: '#fff', padding: '2rem', borderRadius: '8px', display: 'inline-block' }}>
            <h3 style={{ borderBottom: '1px solid #555', paddingBottom: '0.5rem', marginBottom: '1rem' }}>Active Session Identity</h3>
            <div style={{ fontSize: '1.2rem', margin: '0.5rem 0' }}><strong>Role:</strong> {user.business_type || user.role || 'customer'}</div>
            <div style={{ fontSize: '1.2rem', margin: '0.5rem 0', color: '#0dcaf0' }}><strong>Account ID:</strong> {user.email || user.user_id || 'test@gmail.com'}</div>
          </div>
        )}
      </div>
    </div>
  );
}
