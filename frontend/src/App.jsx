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
import Chat from './pages/Chat';
import CompleteProfile from './pages/CompleteProfile';
import Marketplace from './pages/Marketplace';
import OrderTracking from './pages/OrderTracking';
import SellerDashboard from './pages/SellerDashboard';
import SearchBar from './pages/SearchBar';
import SupportTickets from './pages/SupportTickets';
import TicketChat from './pages/TicketChat';
import Layout from './components/Layout';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [kycComplete, setKycComplete] = useState(true); // default true to avoid flash

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
        const res = await axiosClient.get('/api/v1/me');
        console.log("USER FROM /me:", res.data?.user);
        setIsAuthenticated(true);
        setKycComplete(res.data?.user?.kyc_complete ?? true);
      } catch (error) {
        // If both access and refresh fail, interceptor already wiped tokens
        localStorage.clear();
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
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    if (!kycComplete) return <Navigate to="/complete-profile" replace />;
    return children;
  };

  // Layout-wrapped protected route
  const ProtectedWithLayout = ({ children }) => {
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    if (!kycComplete) return <Navigate to="/complete-profile" replace />;
    return <Layout>{children}</Layout>;
  };

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login onLogin={async () => {
          setIsAuthenticated(true);
          try {
            const res = await axiosClient.get('/api/v1/me');
            setKycComplete(res.data?.user?.kyc_complete ?? true);
          } catch { setKycComplete(true); }
        }} />} />
        
        {/* Complete Profile - no layout, requires auth but not KYC */}
        <Route path="/complete-profile" element={
          isAuthenticated ? <CompleteProfile /> : <Navigate to="/login" replace />
        } />

        {/* Routes with sidebar layout */}
        <Route path="/dashboard" element={
          <ProtectedWithLayout>
            <Dashboard />
          </ProtectedWithLayout>
        } />
        
        <Route path="/products" element={
          <ProtectedWithLayout>
            <ProductManager />
          </ProtectedWithLayout>
        } />
        
        <Route path="/contacts" element={
          <ProtectedWithLayout>
            <Contacts />
          </ProtectedWithLayout>
        } />

        <Route path="/inventory" element={
          <ProtectedWithLayout>
            <Inventory />
          </ProtectedWithLayout>
        } />

        <Route path="/profit" element={
          <ProtectedWithLayout>
            <ProfitDashboard />
          </ProtectedWithLayout>
        } />

        <Route path="/billing" element={
          <ProtectedWithLayout>
            <Pricing />
          </ProtectedWithLayout>
        } />

        <Route path="/chat" element={
          <ProtectedWithLayout>
            <Chat />
          </ProtectedWithLayout>
        } />

        <Route path="/marketplace" element={
          <ProtectedWithLayout>
            <Marketplace />
          </ProtectedWithLayout>
        } />

        <Route path="/orders/:orderId" element={
          <ProtectedWithLayout>
            <OrderTracking />
          </ProtectedWithLayout>
        } />

        <Route path="/seller-dashboard" element={
          <ProtectedWithLayout>
            <SellerDashboard />
          </ProtectedWithLayout>
        } />

        <Route path="/search" element={
          <ProtectedWithLayout>
            <SearchBar />
          </ProtectedWithLayout>
        } />

        <Route path="/tickets" element={
          <ProtectedWithLayout>
            <SupportTickets />
          </ProtectedWithLayout>
        } />

        <Route path="/tickets/:ticketId" element={
          <ProtectedWithLayout>
            <TicketChat />
          </ProtectedWithLayout>
        } />

        <Route path="/onboarding" element={
          <ProtectedRoute>
            <Onboarding />
          </ProtectedRoute>
        } />
        
        <Route path="/settings" element={
          <ProtectedWithLayout>
            <Settings />
          </ProtectedWithLayout>
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
