import React, { createContext, useContext, useState, useEffect } from 'react';
import axiosClient from '../api/axiosClient';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [kycComplete, setKycComplete] = useState(true);

  const fetchUser = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setIsInitializing(false);
      return;
    }
    try {
      const res = await axiosClient.get('/api/v1/me');
      setUser(res.data?.user || null);
      setIsAuthenticated(true);
      setKycComplete(res.data?.user?.kyc_complete ?? true);
    } catch (error) {
      localStorage.clear();
      setIsAuthenticated(false);
      setUser(null);
    } finally {
      setIsInitializing(false);
    }
  };

  useEffect(() => {
    fetchUser();
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, isAuthenticated, setIsAuthenticated, isInitializing, kycComplete, setKycComplete, fetchUser }}>
      {children}
    </AuthContext.Provider>
  );
};
