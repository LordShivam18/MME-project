import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import axiosClient from './api/axiosClient';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ProductManager from './pages/ProductManager';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);

  // ACTIVE TOKEN VALIDATION
  useEffect(() => {
    const validateSession = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        setIsInitializing(false);
        return;
      }
      try {
        // Ping explicit backend Auth route to cryptographically verify token
        await axiosClient.get('/auth/me');
        setIsAuthenticated(true);
      } catch (error) {
        // If it throws 401, axiosClient interceptor automatically wipes it
        setIsAuthenticated(false);
      } finally {
        setIsInitializing(false);
      }
    };
    validateSession();
  }, []);

  if (isInitializing) {
    return <div className="spinner-container">Loading Security Context...</div>; // UI State
  }

  // Route wrapper protection
  const ProtectedRoute = ({ children }) => {
    return isAuthenticated ? children : <Navigate to="/login" replace />;
  };

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login onLogin={() => setIsAuthenticated(true)} />} />
        
        {/* Explicit Routing boundaries */}
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        } />
        
        <Route path="/products" element={
          <ProtectedRoute>
            <ProductManager />
          </ProtectedRoute>
        } />
        
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
