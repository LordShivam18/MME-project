import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import Navigation from '../components/Navigation';
import BillingStatus from '../components/BillingStatus';

export default function Pricing() {
  const [searchParams] = useSearchParams();
  const [isUpgrading, setIsUpgrading] = useState(false);
  const [isDowngrading, setIsDowngrading] = useState(false);
  const [message, setMessage] = useState('');
  const [billingInfo, setBillingInfo] = useState(null);
  
  useEffect(() => {
    // Check for success/cancel redirects
    const status = searchParams.get('status');
    if (status === 'success') {
      setMessage('Payment successful! Your subscription is now active.');
    } else if (status === 'cancelled') {
      setMessage('Checkout cancelled. You have not been charged.');
    }
  }, [searchParams]);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await axiosClient.get('/api/v1/billing/status');
        setBillingInfo(res.data);
      } catch (err) {
        console.error('Failed to load billing info', err);
      }
    };
    fetchStatus();
  }, []);

  const handleUpgrade = async () => {
    setIsUpgrading(true);
    setMessage('');
    try {
      const res = await axiosClient.post('/api/v1/billing/create-checkout-session');
      if (res.data.checkout_url) {
        window.location.href = res.data.checkout_url;
      } else if (res.data.redirect) {
        // Fallback or old endpoint format
        window.location.href = res.data.redirect;
      } else {
        // Simulated upgrade success
        setMessage(res.data.message || 'Upgraded successfully!');
        setBillingInfo(prev => ({...prev, plan: 'pro', status: 'active'}));
      }
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Failed to initiate upgrade.');
    } finally {
      setIsUpgrading(false);
    }
  };

  const handleDowngrade = async () => {
    if (!window.confirm('Are you sure you want to downgrade to the Free plan? Some limits will apply.')) return;
    setIsDowngrading(true);
    setMessage('');
    try {
      const res = await axiosClient.post('/api/v1/billing/downgrade');
      setMessage(res.data.message || 'Downgraded to free plan successfully.');
      setBillingInfo(prev => ({...prev, plan: 'free'}));
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Failed to downgrade.');
    } finally {
      setIsDowngrading(false);
    }
  };

  const currentPlan = billingInfo?.plan || 'free';

  return (
    <div style={styles.page}>
      <Navigation />
      
      <div style={styles.content}>
        <div style={styles.header}>
          <h1 style={styles.title}>Pricing & Billing</h1>
          <p style={styles.subtitle}>Choose the plan that fits your business needs.</p>
        </div>

        {message && (
          <div style={{ ...styles.alert, backgroundColor: message.includes('cancelled') || message.includes('Failed') ? '#fee2e2' : '#dcfce7', color: message.includes('cancelled') || message.includes('Failed') ? '#991b1b' : '#166534' }}>
            {message}
          </div>
        )}

        <div style={styles.dashboardSection}>
          <BillingStatus />
        </div>

        <div style={styles.pricingCardsContainer}>
          {/* Free Plan Card */}
          <div style={{ ...styles.card, border: currentPlan === 'free' ? '2px solid #3b82f6' : '1px solid #e5e7eb' }}>
            {currentPlan === 'free' && <div style={styles.currentBadge}>Current Plan</div>}
            <h2 style={styles.cardTitle}>Free Starter</h2>
            <div style={styles.price}>
              <span style={styles.currency}>$</span>0<span style={styles.period}>/month</span>
            </div>
            <ul style={styles.featuresList}>
              <li style={styles.featureItem}>✓ Up to 10 Products</li>
              <li style={styles.featureItem}>✓ Up to 2 Staff Users</li>
              <li style={styles.featureItem}>✓ Basic Inventory Management</li>
              <li style={styles.featureItem}>✕ AI Sales Predictions</li>
            </ul>
            {currentPlan === 'pro' && (
              <button 
                onClick={handleDowngrade} 
                disabled={isDowngrading}
                style={styles.downgradeBtn}
              >
                {isDowngrading ? 'Downgrading...' : 'Downgrade to Free'}
              </button>
            )}
            {currentPlan === 'free' && (
              <button disabled style={styles.activeBtn}>Current Plan</button>
            )}
          </div>

          {/* Pro Plan Card */}
          <div style={{ ...styles.card, border: currentPlan === 'pro' ? '2px solid #8b5cf6' : '1px solid #e5e7eb', boxShadow: '0 10px 15px -3px rgba(139, 92, 246, 0.2)' }}>
            {currentPlan === 'pro' && <div style={{ ...styles.currentBadge, backgroundColor: '#8b5cf6' }}>Current Plan</div>}
            <h2 style={styles.cardTitle}>Pro Business</h2>
            <div style={styles.price}>
              <span style={styles.currency}>$</span>49<span style={styles.period}>/month</span>
            </div>
            <ul style={styles.featuresList}>
              <li style={styles.featureItem}>✓ Unlimited Products</li>
              <li style={styles.featureItem}>✓ Unlimited Staff Users</li>
              <li style={styles.featureItem}>✓ Advanced Inventory Analytics</li>
              <li style={styles.featureItem}>✓ AI Sales Predictions</li>
            </ul>
            {currentPlan === 'free' && (
              <button 
                onClick={handleUpgrade} 
                disabled={isUpgrading}
                style={styles.upgradeBtn}
              >
                {isUpgrading ? 'Redirecting...' : 'Upgrade to Pro'}
              </button>
            )}
            {currentPlan === 'pro' && (
              <button disabled style={{ ...styles.activeBtn, backgroundColor: '#8b5cf6' }}>Current Plan</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    fontFamily: '"Inter", sans-serif',
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '1rem',
    backgroundColor: '#fafafa',
    minHeight: '100vh',
  },
  content: {
    padding: '2rem',
  },
  header: {
    textAlign: 'center',
    marginBottom: '3rem',
  },
  title: {
    fontSize: '2.5rem',
    fontWeight: '800',
    color: '#111827',
    marginBottom: '0.5rem',
  },
  subtitle: {
    fontSize: '1.2rem',
    color: '#6b7280',
  },
  alert: {
    padding: '1rem',
    borderRadius: '8px',
    marginBottom: '2rem',
    textAlign: 'center',
    fontWeight: '500',
  },
  dashboardSection: {
    display: 'flex',
    justifyContent: 'center',
    marginBottom: '3rem',
  },
  pricingCardsContainer: {
    display: 'flex',
    justifyContent: 'center',
    gap: '2rem',
    flexWrap: 'wrap',
  },
  card: {
    position: 'relative',
    backgroundColor: '#ffffff',
    borderRadius: '16px',
    padding: '2.5rem 2rem',
    width: '320px',
    display: 'flex',
    flexDirection: 'column',
    transition: 'transform 0.2s',
    ':hover': {
      transform: 'translateY(-5px)',
    }
  },
  currentBadge: {
    position: 'absolute',
    top: '-12px',
    left: '50%',
    transform: 'translateX(-50%)',
    backgroundColor: '#3b82f6',
    color: '#ffffff',
    padding: '4px 12px',
    borderRadius: '9999px',
    fontSize: '0.8rem',
    fontWeight: 'bold',
    textTransform: 'uppercase',
  },
  cardTitle: {
    fontSize: '1.5rem',
    fontWeight: '700',
    color: '#1f2937',
    textAlign: 'center',
    marginBottom: '1rem',
  },
  price: {
    fontSize: '3rem',
    fontWeight: '800',
    color: '#111827',
    textAlign: 'center',
    marginBottom: '2rem',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'baseline',
  },
  currency: {
    fontSize: '1.5rem',
    fontWeight: '600',
    color: '#4b5563',
  },
  period: {
    fontSize: '1rem',
    fontWeight: '500',
    color: '#6b7280',
    marginLeft: '4px',
  },
  featuresList: {
    listStyle: 'none',
    padding: 0,
    margin: '0 0 2rem 0',
    flexGrow: 1,
  },
  featureItem: {
    fontSize: '1rem',
    color: '#4b5563',
    marginBottom: '1rem',
    display: 'flex',
    alignItems: 'center',
  },
  upgradeBtn: {
    width: '100%',
    padding: '1rem',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#8b5cf6',
    color: '#ffffff',
    fontSize: '1.1rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  downgradeBtn: {
    width: '100%',
    padding: '1rem',
    borderRadius: '8px',
    border: '1px solid #d1d5db',
    backgroundColor: '#ffffff',
    color: '#4b5563',
    fontSize: '1.1rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  activeBtn: {
    width: '100%',
    padding: '1rem',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#3b82f6',
    color: '#ffffff',
    fontSize: '1.1rem',
    fontWeight: '600',
    opacity: 0.8,
    cursor: 'not-allowed',
  }
};
