import React, { createContext, useContext, useEffect, useState } from 'react';
import { getToken, clearToken } from '../utils/storage';
import { setOnUnauthorized } from '../api/client';

interface AuthState {
  isLoading: boolean;
  isAuthenticated: boolean;
  setAuthenticated: (val: boolean) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  isLoading: true,
  isAuthenticated: false,
  setAuthenticated: () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    getToken().then((token) => {
      setAuthenticated(!!token);
      setIsLoading(false);
    });

    setOnUnauthorized(() => {
      setAuthenticated(false);
    });
  }, []);

  const logout = async () => {
    await clearToken();
    setAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ isLoading, isAuthenticated, setAuthenticated, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
