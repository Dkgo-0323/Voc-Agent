"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AUTH_UNAUTHORIZED_EVENT, setApiAccessToken, toApiError } from "@/lib/api/client";
import { fetchAuthIdentity, loginWithPassword, type AuthIdentity } from "@/lib/auth/client";
import { clearAuthToken, readAuthToken, writeAuthToken } from "@/lib/auth/token-storage";

type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

type AuthContextValue = {
  status: AuthStatus;
  user: AuthIdentity | null;
  error: string | null;
  login: (password: string) => Promise<void>;
  logout: () => void;
  retryBootstrap: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function removeSession() {
  clearAuthToken();
  setApiAccessToken(null);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthIdentity | null>(null);
  const [error, setError] = useState<string | null>(null);

  const logout = useCallback(() => {
    removeSession();
    setUser(null);
    setError(null);
    setStatus("unauthenticated");
  }, []);

  const retryBootstrap = useCallback(async () => {
    const token = readAuthToken();
    if (!token) {
      setUser(null);
      setError(null);
      setStatus("unauthenticated");
      return;
    }

    setStatus("loading");
    setError(null);
    setApiAccessToken(token);
    try {
      const identity = await fetchAuthIdentity();
      setUser(identity);
      setStatus("authenticated");
    } catch (caughtError) {
      const apiError = toApiError(caughtError);
      if (apiError.status === 401) {
        removeSession();
        setUser(null);
        setStatus("unauthenticated");
      } else {
        setUser(null);
        setError("Your saved session could not be verified. Please try again.");
        setStatus("error");
      }
    }
  }, []);

  const login = useCallback(async (password: string) => {
    removeSession();
    setError(null);
    try {
      const { access_token: token, token_type: tokenType } = await loginWithPassword(password);
      if (tokenType !== "bearer" || !token) {
        throw new Error("The sign-in response was invalid.");
      }
      writeAuthToken(token);
      setApiAccessToken(token);
      const identity = await fetchAuthIdentity();
      setUser(identity);
      setStatus("authenticated");
    } catch (caughtError) {
      removeSession();
      setUser(null);
      setStatus("unauthenticated");
      throw toApiError(caughtError);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(retryBootstrap);
  }, [retryBootstrap]);

  useEffect(() => {
    const handleUnauthorized = () => logout();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [logout]);

  const value = useMemo(
    () => ({ status, user, error, login, logout, retryBootstrap }),
    [error, login, logout, retryBootstrap, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
