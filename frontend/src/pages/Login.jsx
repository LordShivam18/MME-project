import { useState } from 'react';
import axiosClient from '../api/axiosClient';

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
    <div style={{ maxWidth: '400px', margin: '4rem auto', fontFamily: 'sans-serif', padding: '2rem', border: '1px solid #ccc', borderRadius: '8px' }}>
      <h2>Shop Manager Portal</h2>
      {error && <div style={{ color: 'red', border: '1px solid red', padding: '0.5rem', marginBottom: '1rem' }}>{error}</div>}
      
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <label style={{ display: 'block', marginBottom: '0.2rem' }}>Email / Username</label>
          <input 
            type="email" 
            value={email} 
            onChange={e => setEmail(e.target.value)} 
            required 
            style={{ width: '100%', padding: '0.5rem', boxSizing: 'border-box' }} 
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.2rem' }}>Password</label>
          <input 
            type="password" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
            required 
            style={{ width: '100%', padding: '0.5rem', boxSizing: 'border-box' }} 
          />
        </div>
        <button 
          type="submit" 
          disabled={isLoading}
          style={{ width: '100%', padding: '0.75rem', marginTop: '0.5rem', background: '#333', color: 'white', border: 'none', cursor: 'pointer' }}
        >
          {isLoading ? "Authenticating..." : "Login"}
        </button>
      </form>
    </div>
  );
}
