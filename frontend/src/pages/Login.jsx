import { useState } from 'react';
import axiosClient from '../api/axiosClient';
import './Login.css';

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    
    try {
      // Backend expects standard OAuth2 URL Encoded Form for Auth
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);
      
      const response = await axiosClient.post('/auth/token', formData);
      localStorage.setItem('token', response.data.access_token);
      onLogin(); // Triggers the App route protection wrapper to flip state
    } catch (err) {
      setError(err.response?.data?.detail || "System unable to authenticate. Try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      {/* Ambient background for glassmorphism contrast */}
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
          <h2>Welcome back</h2>
          <p>Sign in to your IMS dashboard.</p>
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
        
        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="email">Email address</label>
            <input 
              id="email"
              type="text" 
              value={email} 
              onChange={e => setEmail(e.target.value)} 
              required 
              placeholder="you@company.com"
              className={error ? 'input-error' : ''}
              autoComplete="username"
            />
          </div>

          <div className="form-group">
            <div className="password-label-row">
               <label htmlFor="password">Password</label>
               <a href="#" className="forgot-password" onClick={(e) => e.preventDefault()}>Forgot password?</a>
            </div>
            <input 
              id="password"
              type="password" 
              value={password} 
              onChange={e => setPassword(e.target.value)} 
              required 
              placeholder="••••••••"
              className={error ? 'input-error' : ''}
              autoComplete="current-password"
            />
          </div>

          <button 
            type="submit" 
            disabled={isLoading}
            className={`login-button ${isLoading ? 'loading' : ''}`}
          >
            {isLoading ? "Signing in..." : "Continue"}
          </button>
          
          <p className="signup-prompt">
            Don't have an account? <a href="#" onClick={(e) => e.preventDefault()}>Contact your admin</a>
          </p>
        </form>
      </div>
    </div>
  );
}
