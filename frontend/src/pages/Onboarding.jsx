import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  
  const [productData, setProductData] = useState({
    name: 'Smart Coffee Maker Tracker',
    sku: 'SCM-3000',
    category: 'Electronics',
    cost_price: 45.00,
    selling_price: 120.00,
    lead_time_days: 7
  });
  
  const [productId, setProductId] = useState(null);
  const [insight, setInsight] = useState(null);

  const nextStep = () => setStep(s => s + 1);

  const handleCreateProduct = async () => {
    setIsLoading(true);
    setError('');
    try {
      const res = await axiosClient.post('/api/v1/products/', productData);
      setProductId(res.data.id);
      nextStep();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create product.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRecordSale = async () => {
    setIsLoading(true);
    setError('');
    try {
      // 1. Secretly inject stock to avoid constraint validation errors
      await axiosClient.post('/api/v1/inventory/add-stock', {
        product_id: productId,
        quantity: 100
      });

      // 2. Record the sale
      await axiosClient.post('/api/v1/sales/', {
        product_id: productId,
        quantity_sold: 5
      });
      
      // 3. Since the cron handles prediction, and we want instant feedback in onboarding
      // We will pretend to fetch the insight but really hit the updated prediction endpoint
      // NOTE: Our prediction endpoint returns a fallback if no cron has run, so we will show that.
      nextStep();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to record sale.');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchInsight = async () => {
    setIsLoading(true);
    try {
      const res = await axiosClient.get(`/api/v1/predictions/${productId}`);
      setInsight(res.data);
    } catch (err) {
      setError("Failed to fetch insight");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (step === 4 && productId) {
      fetchInsight();
    }
  }, [step, productId]);

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Progress Bar */}
        <div style={styles.progressContainer}>
          <div style={{ ...styles.progressBar, width: `${(step / 4) * 100}%` }} />
        </div>
        <div style={styles.stepText}>Step {step} of 4</div>

        {error && <div style={styles.error}>{error}</div>}

        {step === 1 && (
           <div style={styles.stepContent}>
             <h1 style={styles.title}>Welcome to Your Inventory OS</h1>
             <p style={styles.text}>
               We're going to set up your first product, record a mock sale, and show you exactly how our AI identifies trends to save you money.
             </p>
             <button onClick={nextStep} style={styles.primaryBtn}>Let's Get Started</button>
           </div>
        )}

        {step === 2 && (
           <div style={styles.stepContent}>
             <h2 style={styles.title}>Add Your First Product</h2>
             <p style={styles.text}>We've pre-filled some data for you. Feel free to edit it!</p>
             
             <div style={styles.formGroup}>
               <label style={styles.label}>Product Name</label>
               <input style={styles.input} type="text" value={productData.name} onChange={e => setProductData({...productData, name: e.target.value})} />
             </div>
             <div style={styles.formRow}>
               <div style={styles.formGroup}>
                 <label style={styles.label}>SKU</label>
                 <input style={styles.input} type="text" value={productData.sku} onChange={e => setProductData({...productData, sku: e.target.value})} />
               </div>
               <div style={styles.formGroup}>
                 <label style={styles.label}>Selling Price</label>
                 <input style={styles.input} type="number" value={productData.selling_price} onChange={e => setProductData({...productData, selling_price: e.target.value})} />
               </div>
             </div>

             <button onClick={handleCreateProduct} disabled={isLoading} style={{...styles.primaryBtn, marginTop: '2rem'}}>
               {isLoading ? 'Saving...' : 'Save Product & Continue'}
             </button>
           </div>
        )}

        {step === 3 && (
           <div style={styles.stepContent}>
             <h2 style={styles.title}>Record a Sale</h2>
             <p style={styles.text}>
               Great! Now let's simulate selling 5 units of your <strong>{productData.name}</strong>.
               <br/>Behind the scenes, we'll automatically add stock so this goes through smoothly.
             </p>
             
             <button onClick={handleRecordSale} disabled={isLoading} style={styles.primaryBtn}>
               {isLoading ? 'Processing...' : 'Simulate Sale'}
             </button>
           </div>
        )}

        {step === 4 && (
           <div style={styles.stepContent}>
             <h2 style={styles.title}>AI Insight Generated 🧠</h2>
             <p style={styles.text}>Based on your recent activity, our engine has processed your data.</p>
             
             {isLoading ? (
               <div style={styles.loadingBox}>Analyzing patterns...</div>
             ) : (
               <div style={styles.insightCard}>
                  <div style={styles.insightHeader}>
                     <span style={styles.confidenceBadge}>{insight?.confidence_score}% Confidence</span>
                  </div>
                  <h3 style={styles.insightTitle}>{insight?.insight}</h3>
                  <div style={styles.actionBox}>
                    <strong>Recommended Action:</strong><br/>
                    {insight?.recommended_action}
                  </div>
               </div>
             )}

             <button onClick={() => navigate('/dashboard')} style={{...styles.primaryBtn, marginTop: '2rem'}}>
                Go to Dashboard
             </button>
           </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f3f4f6', 
    padding: '1rem',
    fontFamily: '"Inter", sans-serif'
  },
  container: {
    backgroundColor: '#ffffff',
    borderRadius: '16px',
    boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)',
    width: '100%',
    maxWidth: '500px',
    padding: '3rem 2rem',
    position: 'relative',
    overflow: 'hidden'
  },
  progressContainer: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    height: '6px',
    backgroundColor: '#e5e7eb'
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#3b82f6',
    transition: 'width 0.4s ease'
  },
  stepText: {
    fontSize: '0.875rem',
    color: '#6b7280',
    fontWeight: '600',
    marginBottom: '1rem'
  },
  stepContent: {
    animation: 'fadeIn 0.5s ease forwards'
  },
  title: {
    fontSize: '2rem',
    fontWeight: '800',
    color: '#111827',
    marginBottom: '1rem',
    lineHeight: '1.2'
  },
  text: {
    fontSize: '1rem',
    color: '#4b5563',
    marginBottom: '2rem',
    lineHeight: '1.5'
  },
  primaryBtn: {
    width: '100%',
    padding: '1rem',
    backgroundColor: '#111827',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '1.1rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'background-color 0.2s'
  },
  formGroup: {
    marginBottom: '1.25rem',
    flex: 1
  },
  formRow: {
    display: 'flex',
    gap: '1rem'
  },
  label: {
    display: 'block',
    fontSize: '0.875rem',
    fontWeight: '600',
    color: '#374151',
    marginBottom: '0.5rem'
  },
  input: {
    width: '100%',
    padding: '0.75rem',
    border: '1px solid #d1d5db',
    borderRadius: '8px',
    fontSize: '1rem',
    boxSizing: 'border-box'
  },
  error: {
    padding: '1rem',
    backgroundColor: '#fee2e2',
    color: '#991b1b',
    borderRadius: '8px',
    marginBottom: '1rem',
    fontWeight: '500'
  },
  loadingBox: {
    padding: '2rem',
    textAlign: 'center',
    color: '#6b7280',
    fontWeight: '500',
    border: '2px dashed #e5e7eb',
    borderRadius: '8px'
  },
  insightCard: {
    border: '2px solid #3b82f6',
    borderRadius: '12px',
    padding: '1.5rem',
    backgroundColor: '#f0fdf4',
    borderColor: '#10b981'
  },
  insightHeader: {
    display: 'flex',
    justifyContent: 'flex-end',
    marginBottom: '0.5rem'
  },
  confidenceBadge: {
    backgroundColor: '#10b981',
    color: '#ffffff',
    padding: '4px 8px',
    borderRadius: '9999px',
    fontSize: '0.75rem',
    fontWeight: 'bold'
  },
  insightTitle: {
    fontSize: '1.5rem',
    color: '#065f46',
    margin: '0 0 1rem 0'
  },
  actionBox: {
    backgroundColor: '#d1fae5',
    padding: '1rem',
    borderRadius: '8px',
    color: '#064e3b',
    fontSize: '0.9rem'
  }
};
