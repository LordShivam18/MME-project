import { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

export default function BillingStatus() {
  const [billingInfo, setBillingInfo] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBillingStatus = async () => {
      try {
        const res = await axiosClient.get('/api/v1/billing/status');
        setBillingInfo(res.data);
      } catch (err) {
        console.error('Error fetching billing status', err);
        setError('Failed to load billing status.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchBillingStatus();
  }, []);

  if (isLoading) return <div style={styles.container}>Loading billing status...</div>;
  if (error) return <div style={{...styles.container, color: '#dc3545'}}>{error}</div>;
  if (!billingInfo) return null;

  const { plan, status, limits, usage, expiry } = billingInfo;
  
  const isPro = plan === 'pro';

  return (
    <div style={styles.container}>
      <h3 style={styles.header}>Current Plan: <span style={{ textTransform: 'capitalize', color: isPro ? '#8b5cf6' : '#10b981' }}>{plan}</span></h3>
      <div style={styles.statusRow}>
        Status: <span style={{ fontWeight: 'bold', color: status === 'active' ? '#10b981' : '#f59e0b' }}>{status.toUpperCase()}</span>
      </div>
      {expiry && (
        <div style={styles.statusRow}>
          <span style={{ fontWeight: '600' }}>
            {status === 'expired' ? 'Expired on:' : (plan === 'free' ? 'Access until:' : 'Next Billing Date:')}
          </span>{' '}
          {new Date(expiry).toLocaleDateString()}
        </div>
      )}
      
      <div style={styles.usageContainer}>
        <div style={styles.usageItem}>
          <span style={styles.usageLabel}>Products Usage:</span>
          <span>
            {usage.products} / {limits.max_products === null ? '∞' : limits.max_products}
          </span>
          {limits.max_products !== null && (
            <>
              <div style={styles.progressBarBg}>
                <div style={{ ...styles.progressBarFill, width: `${Math.min(100, (usage.products / limits.max_products) * 100)}%`, backgroundColor: usage.products >= limits.max_products ? '#ef4444' : (usage.products / limits.max_products >= 0.8 ? '#f59e0b' : '#3b82f6') }} />
              </div>
              {usage.products / limits.max_products >= 0.8 && usage.products < limits.max_products && <div style={{color: '#f59e0b', fontSize: '0.75rem', marginTop: '0.25rem'}}>Approaching limit (80%+)</div>}
              {usage.products >= limits.max_products && <div style={{color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem'}}>Limit reached</div>}
            </>
          )}
        </div>
        <div style={styles.usageItem}>
          <span style={styles.usageLabel}>Users Usage:</span>
          <span>
            {usage.users} / {limits.max_users === null ? '∞' : limits.max_users}
          </span>
          {limits.max_users !== null && (
             <>
               <div style={styles.progressBarBg}>
                 <div style={{ ...styles.progressBarFill, width: `${Math.min(100, (usage.users / limits.max_users) * 100)}%`, backgroundColor: usage.users >= limits.max_users ? '#ef4444' : (usage.users / limits.max_users >= 0.8 ? '#f59e0b' : '#3b82f6') }} />
               </div>
               {usage.users / limits.max_users >= 0.8 && usage.users < limits.max_users && <div style={{color: '#f59e0b', fontSize: '0.75rem', marginTop: '0.25rem'}}>Approaching limit (80%+)</div>}
               {usage.users >= limits.max_users && <div style={{color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem'}}>Limit reached</div>}
             </>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '1.5rem',
    borderRadius: '12px',
    backgroundColor: '#ffffff',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    border: '1px solid #e5e7eb',
    marginBottom: '2rem',
    maxWidth: '400px'
  },
  header: {
    margin: '0 0 1rem 0',
    fontSize: '1.25rem',
    color: '#1f2937'
  },
  statusRow: {
    fontSize: '0.875rem',
    color: '#4b5563',
    marginBottom: '0.5rem'
  },
  usageContainer: {
    marginTop: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem'
  },
  usageItem: {
    display: 'flex',
    flexDirection: 'column',
    fontSize: '0.875rem',
    color: '#374151'
  },
  usageLabel: {
    fontWeight: '600',
    marginBottom: '0.25rem'
  },
  progressBarBg: {
    width: '100%',
    height: '8px',
    backgroundColor: '#e5e7eb',
    borderRadius: '9999px',
    marginTop: '0.5rem',
    overflow: 'hidden'
  },
  progressBarFill: {
    height: '100%',
    transition: 'width 0.3s ease'
  }
};
