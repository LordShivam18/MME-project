import React, { useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import { LoadingSpinner, ErrorState } from '../components/StateSpinners';

export default function Settings() {
  const [user, setUser] = useState(null);
  const [org, setOrg] = useState(null);
  const [aiMode, setAiMode] = useState("balanced");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    const fetchMe = async () => {
      try {
        const res = await axiosClient.get('/api/v1/me');
        setUser(res.data?.user || null);
        setOrg(res.data?.organization || null);
        if (res.data?.organization?.ai_decision_mode) {
          setAiMode(res.data.organization.ai_decision_mode);
        }
      } catch (err) {
        console.error(err);
        setError("Unable to load settings.");
      } finally {
        setIsLoading(false);
      }
    };
    fetchMe();
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

  return (
    <div style={{ fontFamily: '"Inter", sans-serif', maxWidth: '1200px', margin: '0 auto', padding: '1rem' }}>
      
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
