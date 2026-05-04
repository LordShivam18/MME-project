import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';

const ROLES = [
  { value: 'supplier', icon: '🏭', label: 'Supplier Business', desc: 'I manufacture or source products' },
  { value: 'wholesaler', icon: '📦', label: 'Wholesaler Business', desc: 'I buy in bulk and resell' },
  { value: 'retailer', icon: '🏪', label: 'Retailer Business', desc: 'I sell directly to consumers' },
  { value: 'customer', icon: '🛒', label: 'Customer', desc: 'I want to browse and buy products' },
  { value: 'other', icon: '✨', label: 'Other', desc: 'Custom role' },
];

export default function CompleteProfile() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [selectedRole, setSelectedRole] = useState('');
  const [customRole, setCustomRole] = useState('');
  const [formData, setFormData] = useState({ full_name: '', age: '', phone: '', address: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!formData.full_name.trim()) {
      setError('Full name is required');
      return;
    }
    setIsLoading(true);
    setError('');
    try {
      await axiosClient.post('/api/v1/auth/complete-profile', {
        business_type: selectedRole,
        custom_role: selectedRole === 'other' ? customRole : undefined,
        full_name: formData.full_name,
        age: formData.age ? parseInt(formData.age) : undefined,
        phone: formData.phone || undefined,
        address: formData.address || undefined,
      });
      // Sync state globally and debug
      const meRes = await axiosClient.get('/api/v1/me');
      console.log("USER STATE:", meRes.data?.user);
      // Hard redirect to force App.jsx to pick up new session state
      window.location.href = '/dashboard';
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save profile');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.progressWrap}>
          <div style={{ ...s.progressBar, width: `${(step / 2) * 100}%` }} />
        </div>
        <div style={s.stepLabel}>Step {step} of 2</div>

        {error && <div style={s.error}>{error}</div>}

        {step === 1 && (
          <div>
            <h1 style={s.title}>You are?</h1>
            <p style={s.subtitle}>Select your business type to personalize your experience</p>
            <div style={s.roleGrid}>
              {ROLES.map(r => (
                <button
                  key={r.value}
                  onClick={() => setSelectedRole(r.value)}
                  style={{
                    ...s.roleCard,
                    borderColor: selectedRole === r.value ? '#3b82f6' : '#e5e7eb',
                    backgroundColor: selectedRole === r.value ? '#eff6ff' : '#fff',
                    boxShadow: selectedRole === r.value ? '0 0 0 3px rgba(59,130,246,0.1)' : 'none',
                  }}
                >
                  <span style={{ fontSize: '2rem' }}>{r.icon}</span>
                  <strong style={{ color: '#1e293b', fontSize: '0.95rem' }}>{r.label}</strong>
                  <span style={{ color: '#64748b', fontSize: '0.8rem' }}>{r.desc}</span>
                </button>
              ))}
            </div>
            {selectedRole === 'other' && (
              <input
                style={{ ...s.input, marginTop: '1rem' }}
                placeholder="Enter your custom role..."
                value={customRole}
                onChange={e => setCustomRole(e.target.value)}
              />
            )}
            <button
              onClick={() => { if (selectedRole) setStep(2); }}
              disabled={!selectedRole || (selectedRole === 'other' && !customRole.trim())}
              style={{ ...s.btn, marginTop: '1.5rem', opacity: selectedRole ? 1 : 0.5 }}
            >
              Continue
            </button>
          </div>
        )}

        {step === 2 && (
          <div>
            <h1 style={s.title}>Complete Your Profile</h1>
            <p style={s.subtitle}>Tell us a bit about yourself</p>

            <div style={s.field}>
              <label style={s.label}>Full Legal Name *</label>
              <input style={s.input} value={formData.full_name} onChange={e => setFormData({...formData, full_name: e.target.value})} placeholder="John Doe" />
            </div>

            <div style={s.row}>
              <div style={s.field}>
                <label style={s.label}>Age</label>
                <input style={s.input} type="number" value={formData.age} onChange={e => setFormData({...formData, age: e.target.value})} placeholder="25" />
              </div>
              <div style={s.field}>
                <label style={s.label}>Phone</label>
                <input style={s.input} value={formData.phone} onChange={e => setFormData({...formData, phone: e.target.value})} placeholder="+91 9876543210" />
              </div>
            </div>

            <div style={s.field}>
              <label style={s.label}>Address</label>
              <textarea style={{ ...s.input, minHeight: '80px', resize: 'vertical' }} value={formData.address} onChange={e => setFormData({...formData, address: e.target.value})} placeholder="Your business or home address" />
            </div>

            <div style={{ display: 'flex', gap: '1rem', marginTop: '1.5rem' }}>
              <button onClick={() => setStep(1)} style={{ ...s.btn, backgroundColor: '#f1f5f9', color: '#334155', flex: 1 }}>Back</button>
              <button onClick={handleSubmit} disabled={isLoading} style={{ ...s.btn, flex: 2 }}>
                {isLoading ? 'Saving...' : 'Complete Profile'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const s = {
  page: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', fontFamily: '"Inter", sans-serif', padding: '1rem' },
  card: { backgroundColor: '#fff', borderRadius: '16px', boxShadow: '0 10px 40px rgba(0,0,0,0.08)', width: '100%', maxWidth: '540px', padding: '2.5rem 2rem', position: 'relative', overflow: 'hidden' },
  progressWrap: { position: 'absolute', top: 0, left: 0, right: 0, height: '5px', backgroundColor: '#e5e7eb' },
  progressBar: { height: '100%', backgroundColor: '#3b82f6', transition: 'width 0.4s ease', borderRadius: '0 2px 2px 0' },
  stepLabel: { fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, marginBottom: '0.5rem' },
  title: { fontSize: '1.8rem', fontWeight: 800, color: '#0f172a', margin: '0 0 0.5rem 0' },
  subtitle: { fontSize: '0.95rem', color: '#64748b', marginBottom: '1.5rem' },
  roleGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' },
  roleCard: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.4rem', padding: '1.2rem 0.75rem', border: '2px solid', borderRadius: '12px', cursor: 'pointer', transition: 'all 0.2s', background: 'none', textAlign: 'center' },
  field: { marginBottom: '1rem', flex: 1 },
  row: { display: 'flex', gap: '1rem' },
  label: { display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' },
  input: { width: '100%', padding: '0.75rem', border: '1px solid #d1d5db', borderRadius: '8px', fontSize: '0.95rem', boxSizing: 'border-box', outline: 'none', transition: 'border 0.2s' },
  btn: { width: '100%', padding: '0.85rem', backgroundColor: '#0f172a', color: '#fff', border: 'none', borderRadius: '8px', fontSize: '1rem', fontWeight: 600, cursor: 'pointer', transition: 'opacity 0.2s' },
  error: { padding: '0.75rem 1rem', backgroundColor: '#fef2f2', color: '#991b1b', borderRadius: '8px', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: 500, border: '1px solid #fecaca' },
};
