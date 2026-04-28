import { useState } from 'react';
import axiosClient from '../api/axiosClient';
import './Login.css';

// Views: login, signup, otp, forgot, forgot_otp
export default function Login({ onLogin }) {
  const [view, setView] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const resetForm = () => {
    setError('');
    setSuccess('');
    setOtp('');
    setNewPassword('');
  };

  // --- LOGIN ---
  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);
      const response = await axiosClient.post('/api/v1/login', formData);
      if (response.status === 200) {
        localStorage.setItem("access_token", response.data.access_token);
        localStorage.setItem("refresh_token", response.data.refresh_token);
        try {
          const meRes = await axiosClient.get('/api/v1/me');
          if (meRes.data?.user?.is_platform_admin) {
            window.location.href = "/admin";
            return;
          }
        } catch (e) { /* ignore */ }
        try {
          const prodsRes = await axiosClient.get('/api/v1/products/');
          if (prodsRes.data?.length === 0) {
            window.location.href = "/onboarding";
            return;
          }
        } catch (e) { /* ignore */ }
        window.location.href = "/dashboard";
      }
    } catch (err) {
      setError(err.response?.data?.detail || "System unable to authenticate. Try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // --- SIGNUP INITIATE ---
  const handleSignupInitiate = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await axiosClient.post('/api/v1/auth/signup/initiate', { email, password });
      setSuccess('Verification code sent to your email.');
      setView('otp');
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate signup");
    } finally {
      setIsLoading(false);
    }
  };

  // --- SIGNUP VERIFY ---
  const handleSignupVerify = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      const res = await axiosClient.post('/api/v1/auth/signup/verify', { email, otp, password });
      localStorage.setItem("access_token", res.data.access_token);
      localStorage.setItem("refresh_token", res.data.refresh_token);
      window.location.href = "/onboarding";
    } catch (err) {
      setError(err.response?.data?.detail || "Verification failed");
    } finally {
      setIsLoading(false);
    }
  };

  // --- FORGOT INITIATE ---
  const handleForgotInitiate = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await axiosClient.post('/api/v1/auth/forgot/initiate', { email });
      setSuccess('If an account exists, a reset code has been sent.');
      setView('forgot_otp');
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to send reset code");
    } finally {
      setIsLoading(false);
    }
  };

  // --- FORGOT VERIFY ---
  const handleForgotVerify = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await axiosClient.post('/api/v1/auth/forgot/verify', { email, otp, new_password: newPassword });
      setSuccess('Password reset successful!');
      setTimeout(() => { setView('login'); resetForm(); }, 1500);
    } catch (err) {
      setError(err.response?.data?.detail || "Reset failed");
    } finally {
      setIsLoading(false);
    }
  };

  // --- GOOGLE LOGIN ---
  const handleGoogleLogin = async () => {
    setError('');
    try {
      if (!window.google) {
        setError("Google Sign-In not available");
        return;
      }
      window.google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
        callback: async (response) => {
          try {
            const res = await axiosClient.post('/api/v1/auth/google', { id_token: response.credential });
            localStorage.setItem("access_token", res.data.access_token);
            localStorage.setItem("refresh_token", res.data.refresh_token);
            window.location.href = "/dashboard";
          } catch (err) {
            setError(err.response?.data?.detail || "Google login failed");
          }
        }
      });
      window.google.accounts.id.prompt();
    } catch (err) {
      setError("Google login unavailable");
    }
  };

  return (
    <div className="login-wrapper">
      <div className="ambient-background">
        <div className="blob-1"></div>
        <div className="blob-2"></div>
      </div>

      <div className="login-container glass-panel">
        <div className="login-header">
          <div className="login-logo-container">
            <div className="login-logo">
              <span role="img" aria-label="box">📦</span>
            </div>
          </div>
          <h2>
            {view === 'login' && 'Welcome back'}
            {view === 'signup' && 'Create account'}
            {view === 'otp' && 'Verify your email'}
            {view === 'forgot' && 'Reset password'}
            {view === 'forgot_otp' && 'Enter reset code'}
          </h2>
          <p>
            {view === 'login' && 'Sign in to your IMS dashboard.'}
            {view === 'signup' && 'Start managing your inventory.'}
            {view === 'otp' && `We sent a code to ${email}`}
            {view === 'forgot' && 'Enter your email to receive a reset code.'}
            {view === 'forgot_otp' && `Enter the code sent to ${email}`}
          </p>
        </div>

        {error && (
          <div className="login-error" role="alert">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div style={{ padding: '0.75rem 1rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem', marginBottom: '1rem' }}>
            ✅ {success}
          </div>
        )}

        {/* LOGIN VIEW */}
        {view === 'login' && (
          <form onSubmit={handleLogin} className="login-form">
            <div className="form-group">
              <label htmlFor="email">Email address or Username</label>
              <input id="email" type="text" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.com" autoComplete="username" />
            </div>
            <div className="form-group">
              <div className="password-label-row">
                <label htmlFor="password">Password</label>
                <a href="#" className="forgot-password" onClick={(e) => { e.preventDefault(); resetForm(); setView('forgot'); }}>Forgot password?</a>
              </div>
              <input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" autoComplete="current-password" />
            </div>
            <button type="submit" disabled={isLoading} className={`login-button ${isLoading ? 'loading' : ''}`}>
              {isLoading ? "Signing in..." : "Continue"}
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '1rem 0' }}>
              <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }}></div>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>or</span>
              <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }}></div>
            </div>

            <button type="button" onClick={handleGoogleLogin} 
              disabled={!import.meta.env.VITE_GOOGLE_CLIENT_ID}
              title={!import.meta.env.VITE_GOOGLE_CLIENT_ID ? 'Google login not configured' : ''}
              style={{
              width: '100%', padding: '0.7rem', border: '1px solid #d1d5db', borderRadius: '8px',
              background: '#fff', cursor: import.meta.env.VITE_GOOGLE_CLIENT_ID ? 'pointer' : 'not-allowed', 
              fontSize: '0.9rem', fontWeight: 600,
              color: '#374151', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
              opacity: import.meta.env.VITE_GOOGLE_CLIENT_ID ? 1 : 0.5
            }}>
              <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20H24v8h11.3C34 33.3 29.5 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.7 1.1 7.8 2.9l5.7-5.7C33.9 5.5 29.2 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.7-.4-4z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.3 16.1 18.8 13 24 13c3 0 5.7 1.1 7.8 2.9l5.7-5.7C33.9 5.5 29.2 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-1.8 13.4-4.7l-6.2-5.2C29.3 35.9 26.8 37 24 37c-5.5 0-10.1-3.7-11.7-8.7l-6.5 5C9.5 39.5 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20H24v8h11.3c-.8 2.5-2.4 4.6-4.5 6.1l6.2 5.2C40.3 36.3 44 30.7 44 24c0-1.3-.1-2.7-.4-4z"/></svg>
              Continue with Google
            </button>

            <p className="signup-prompt">
              Don't have an account? <a href="#" onClick={(e) => { e.preventDefault(); resetForm(); setView('signup'); }}>Sign up</a>
            </p>
          </form>
        )}

        {/* SIGNUP VIEW */}
        {view === 'signup' && (
          <form onSubmit={handleSignupInitiate} className="login-form">
            <div className="form-group">
              <label htmlFor="signup-email">Email address</label>
              <input id="signup-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.com" />
            </div>
            <div className="form-group">
              <label htmlFor="signup-password">Password (min 8 chars)</label>
              <input id="signup-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" minLength={8} />
            </div>
            <button type="submit" disabled={isLoading} className={`login-button ${isLoading ? 'loading' : ''}`}>
              {isLoading ? "Sending code..." : "Send Verification Code"}
            </button>
            <p className="signup-prompt">
              Already have an account? <a href="#" onClick={(e) => { e.preventDefault(); resetForm(); setView('login'); }}>Sign in</a>
            </p>
          </form>
        )}

        {/* OTP VERIFICATION VIEW */}
        {view === 'otp' && (
          <form onSubmit={handleSignupVerify} className="login-form">
            <div className="form-group">
              <label htmlFor="otp-code">6-digit verification code</label>
              <input id="otp-code" type="text" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} required placeholder="000000"
                style={{ letterSpacing: '8px', textAlign: 'center', fontSize: '1.5rem', fontWeight: 700 }} maxLength={6} />
            </div>
            <button type="submit" disabled={isLoading || otp.length !== 6} className={`login-button ${isLoading ? 'loading' : ''}`}>
              {isLoading ? "Verifying..." : "Create Account"}
            </button>
            <p className="signup-prompt">
              <a href="#" onClick={(e) => { e.preventDefault(); resetForm(); setView('signup'); }}>← Back</a>
            </p>
          </form>
        )}

        {/* FORGOT PASSWORD VIEW */}
        {view === 'forgot' && (
          <form onSubmit={handleForgotInitiate} className="login-form">
            <div className="form-group">
              <label htmlFor="forgot-email">Email address</label>
              <input id="forgot-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.com" />
            </div>
            <button type="submit" disabled={isLoading} className={`login-button ${isLoading ? 'loading' : ''}`}>
              {isLoading ? "Sending..." : "Send Reset Code"}
            </button>
            <p className="signup-prompt">
              <a href="#" onClick={(e) => { e.preventDefault(); resetForm(); setView('login'); }}>← Back to login</a>
            </p>
          </form>
        )}

        {/* FORGOT OTP + NEW PASSWORD VIEW */}
        {view === 'forgot_otp' && (
          <form onSubmit={handleForgotVerify} className="login-form">
            <div className="form-group">
              <label htmlFor="reset-otp">6-digit reset code</label>
              <input id="reset-otp" type="text" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} required placeholder="000000"
                style={{ letterSpacing: '8px', textAlign: 'center', fontSize: '1.5rem', fontWeight: 700 }} maxLength={6} />
            </div>
            <div className="form-group">
              <label htmlFor="new-password">New password (min 8 chars)</label>
              <input id="new-password" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required placeholder="••••••••" minLength={8} />
            </div>
            <button type="submit" disabled={isLoading || otp.length !== 6} className={`login-button ${isLoading ? 'loading' : ''}`}>
              {isLoading ? "Resetting..." : "Reset Password"}
            </button>
            <p className="signup-prompt">
              <a href="#" onClick={(e) => { e.preventDefault(); resetForm(); setView('login'); }}>← Back to login</a>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
