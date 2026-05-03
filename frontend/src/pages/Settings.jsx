import React, { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

export default function Settings() {
  const [user, setUser] = useState(null);
  const [org, setOrg] = useState(null);
  const [aiMode, setAiMode] = useState("balanced");
  const [kyc, setKyc] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [meRes, kycRes] = await Promise.all([
          axiosClient.get('/api/v1/me'),
          axiosClient.get('/api/v1/me/kyc'),
        ]);
        setUser(meRes.data?.user || null);
        setOrg(meRes.data?.organization || null);
        if (meRes.data?.organization?.ai_decision_mode) {
          setAiMode(meRes.data.organization.ai_decision_mode);
        }
        setKyc(kycRes.data?.kyc || null);
      } catch (err) {
        console.error(err);
        setError("Unable to load settings.");
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await axiosClient.patch('/api/v1/settings/ai-mode', { ai_decision_mode: aiMode });
      setSuccess("AI Decision Mode updated successfully!");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save settings. Make sure you are an admin.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingSpinner />
      </div>
    );
  }

  const BUSINESS_LABELS = {
    supplier: '🏭 Supplier',
    wholesaler: '📦 Wholesaler',
    retailer: '🏪 Retailer',
    customer: '🛒 Customer',
  };

  return (
    <div style={{ fontFamily: '"Inter", sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      
      {/* Profile Section */}
      <div style={{ padding: '2rem', marginTop: '1rem', backgroundColor: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
        <h2 style={{ margin: '0 0 1.5rem 0', color: '#0f172a' }}>Profile</h2>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          <div style={cardStyle}>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Account</div>
            <div style={{ marginTop: '1rem' }}>
              <div style={fieldStyle}>
                <span style={fieldLabel}>Email</span>
                <span style={fieldValue}>{user?.sub || user?.email || '—'}</span>
              </div>
              <div style={fieldStyle}>
                <span style={fieldLabel}>Full Name</span>
                <span style={fieldValue}>{user?.full_name || kyc?.full_name || '—'}</span>
              </div>
              <div style={fieldStyle}>
                <span style={fieldLabel}>Role</span>
                <span style={fieldValue}>{user?.role || '—'}</span>
              </div>
              <div style={fieldStyle}>
                <span style={fieldLabel}>Business Type</span>
                <span style={{ ...fieldValue, fontWeight: 600 }}>
                  {BUSINESS_LABELS[user?.business_type] || user?.business_type || '—'}
                </span>
              </div>
            </div>
          </div>

          <div style={cardStyle}>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>KYC Details</div>
            {kyc ? (
              <div style={{ marginTop: '1rem' }}>
                <div style={fieldStyle}>
                  <span style={fieldLabel}>Phone</span>
                  <span style={fieldValue}>{kyc.phone || '—'}</span>
                </div>
                <div style={fieldStyle}>
                  <span style={fieldLabel}>Age</span>
                  <span style={fieldValue}>{kyc.age || '—'}</span>
                </div>
                <div style={fieldStyle}>
                  <span style={fieldLabel}>Address</span>
                  <span style={fieldValue}>{kyc.address || '—'}</span>
                </div>
                <div style={{ marginTop: '0.75rem' }}>
                  <span style={{ padding: '3px 10px', backgroundColor: '#d1fae5', color: '#065f46', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
                    ✓ KYC Verified
                  </span>
                </div>
              </div>
            ) : (
              <div style={{ marginTop: '1rem', color: '#94a3b8', fontSize: '0.9rem' }}>
                No KYC data on file.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Store Visibility Section */}
      {user?.role === 'admin' && (
        <div style={{ padding: '2rem', marginTop: '2rem', backgroundColor: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <h2 style={{ margin: '0 0 1.5rem 0', color: '#0f172a' }}>Store Visibility</h2>
          <div style={cardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong style={{ color: '#1e293b' }}>Make my store visible to customers</strong>
                <p style={{ color: '#64748b', fontSize: '0.85rem', margin: '0.25rem 0 0 0' }}>
                  When enabled, your store and products appear in the public marketplace.
                </p>
              </div>
              <label style={{ position: 'relative', display: 'inline-block', width: '50px', height: '28px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={org?.is_public || false}
                  onChange={async (e) => {
                    try {
                      await axiosClient.patch('/api/v1/organization/visibility', { is_public: e.target.checked });
                      setOrg(prev => ({ ...prev, is_public: e.target.checked }));
                      setSuccess(e.target.checked ? 'Store is now public!' : 'Store is now private');
                      setTimeout(() => setSuccess(null), 3000);
                    } catch (err) {
                      setError(err.response?.data?.detail || 'Failed to update visibility');
                    }
                  }}
                  style={{ opacity: 0, width: 0, height: 0 }}
                />
                <span style={{
                  position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                  backgroundColor: org?.is_public ? '#10b981' : '#cbd5e1',
                  borderRadius: '14px', transition: 'all 0.3s',
                }}>
                  <span style={{
                    position: 'absolute', content: '""', height: '22px', width: '22px',
                    left: org?.is_public ? '25px' : '3px', bottom: '3px',
                    backgroundColor: '#fff', borderRadius: '50%', transition: 'all 0.3s',
                  }} />
                </span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* AI Settings Section */}
      <div style={{ padding: '2rem', marginTop: '2rem', backgroundColor: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
        <h2 style={{ margin: '0 0 1.5rem 0', color: '#0f172a' }}>Organization Settings</h2>
        
        {error && <ErrorState message={error} />}
        {success && <div style={{ padding: '1rem', background: '#d1fae5', color: '#065f46', borderRadius: '8px', marginBottom: '1rem' }}>{success}</div>}

        <div style={{ background: '#ffffff', padding: '2rem', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '2rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', color: '#1e293b' }}>AI Decision Engine Mode</h3>
          <p style={{ color: '#64748b', marginBottom: '1.5rem' }}>
            Adjust how aggressive the AI should be when suggesting order quantities. This acts as a multiplier on top of the base demand prediction.
          </p>
          
          <div style={{ display: 'flex', gap: '1rem', flexDirection: 'column', maxWidth: '400px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1rem', border: '1px solid', borderColor: aiMode === 'conservative' ? '#3b82f6' : '#e2e8f0', borderRadius: '8px', cursor: 'pointer', background: aiMode === 'conservative' ? '#eff6ff' : '#fff' }}>
              <input type="radio" name="aiMode" value="conservative" checked={aiMode === 'conservative'} onChange={(e) => setAiMode(e.target.value)} />
              <div>
                <strong style={{ display: 'block', color: '#0f172a' }}>Conservative (1.2x)</strong>
                <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Over-orders slightly to prioritize preventing stockouts.</span>
              </div>
            </label>
            
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1rem', border: '1px solid', borderColor: aiMode === 'balanced' ? '#3b82f6' : '#e2e8f0', borderRadius: '8px', cursor: 'pointer', background: aiMode === 'balanced' ? '#eff6ff' : '#fff' }}>
              <input type="radio" name="aiMode" value="balanced" checked={aiMode === 'balanced'} onChange={(e) => setAiMode(e.target.value)} />
              <div>
                <strong style={{ display: 'block', color: '#0f172a' }}>Balanced (1.0x)</strong>
                <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Standard JIT prediction. Balances stockout risk and capital lockup.</span>
              </div>
            </label>
            
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1rem', border: '1px solid', borderColor: aiMode === 'aggressive' ? '#3b82f6' : '#e2e8f0', borderRadius: '8px', cursor: 'pointer', background: aiMode === 'aggressive' ? '#eff6ff' : '#fff' }}>
              <input type="radio" name="aiMode" value="aggressive" checked={aiMode === 'aggressive'} onChange={(e) => setAiMode(e.target.value)} />
              <div>
                <strong style={{ display: 'block', color: '#0f172a' }}>Aggressive (0.85x)</strong>
                <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Under-orders slightly to prioritize lean inventory and max capital.</span>
              </div>
            </label>
          </div>
          
          <div style={{ marginTop: '2rem' }}>
            <button 
              onClick={handleSave} 
              disabled={isSaving || user?.role !== 'admin'}
              style={{ background: '#3b82f6', color: 'white', padding: '0.75rem 1.5rem', borderRadius: '8px', cursor: (isSaving || user?.role !== 'admin') ? 'not-allowed' : 'pointer', border: 'none', fontWeight: 600, opacity: (isSaving || user?.role !== 'admin') ? 0.7 : 1 }}
            >
              {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
            {user?.role !== 'admin' && <span style={{ marginLeft: '1rem', color: '#ef4444', fontSize: '0.85rem' }}>Must be an admin to change settings.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

const cardStyle = {
  backgroundColor: '#fff',
  borderRadius: '10px',
  padding: '1.5rem',
  border: '1px solid #e2e8f0',
};

const fieldStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  padding: '0.6rem 0',
  borderBottom: '1px solid #f1f5f9',
};

const fieldLabel = {
  fontSize: '0.875rem',
  color: '#64748b',
};

const fieldValue = {
  fontSize: '0.875rem',
  color: '#1e293b',
};
