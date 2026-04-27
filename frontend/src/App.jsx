import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import axiosClient from './api/axiosClient';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ProductManager from './pages/ProductManager';
import Inventory from './pages/Inventory';
import Pricing from './pages/Pricing';
import Onboarding from './pages/Onboarding';
import Contacts from './pages/Contacts';
import ProfitDashboard from './pages/ProfitDashboard';
import Settings from './pages/Settings';
import AdminDashboard from './pages/AdminDashboard';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);

  // ACTIVE TOKEN VALIDATION
  useEffect(() => {
    const validateSession = async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setIsInitializing(false);
        return;
      }
      try {
        // Ping explicit backend Auth route to cryptographically verify token
        // If access_token is expired, the axiosClient interceptor will silently refresh it
        await axiosClient.get('/api/v1/me');
        setIsAuthenticated(true);
      } catch (error) {
        // If both access and refresh fail, interceptor already wiped tokens
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
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
        
        <Route path="/contacts" element={
          <ProtectedRoute>
            <Contacts />
          </ProtectedRoute>
        } />

        <Route path="/inventory" element={
          <ProtectedRoute>
            <Inventory />
          </ProtectedRoute>
        } />

        <Route path="/profit" element={
          <ProtectedRoute>
            <ProfitDashboard />
          </ProtectedRoute>
        } />

        <Route path="/billing" element={
          <ProtectedRoute>
            <Pricing />
          </ProtectedRoute>
        } />

        <Route path="/onboarding" element={
          <ProtectedRoute>
            <Onboarding />
          </ProtectedRoute>
        } />
        
        <Route path="/settings" element={
          <ProtectedRoute>
            <Settings />
          </ProtectedRoute>
        } />
        
        <Route path="/admin" element={
          <ProtectedRoute>
            <AdminDashboard />
          </ProtectedRoute>
        } />
        
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
