// ui/src/AuthWrapper.tsx
// Authentication wrapper for MarketSwarm

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import LoginPage from './components/LoginPage';

/* =========================================================
   PUBLIC MODE SWITCH
   Set to true to disable auth entirely (development/demo)
   ========================================================= */
const PUBLIC_MODE = false; // Set to true to bypass auth
/* ========================================================= */

// SSE Gateway URL (same as used in App.tsx)
// Use relative URLs - vite proxy handles /api/* in dev
const API_BASE = '';

type AuthStatus = 'loading' | 'authed' | 'unauthed';

interface AuthState {
  status: AuthStatus;
  user?: {
    wp?: {
      issuer?: string;
      id?: string;
      email?: string;
      name?: string;
      roles?: string[];
    };
    iat?: number;
    exp?: number;
  } | null;
}

interface AuthWrapperProps {
  children: ReactNode;
}

/**
 * Check if user has admin role
 */
export function isAdmin(user: AuthState['user']): boolean {
  if (!user) return false;
  const roles = user?.wp?.roles || [];
  return Array.isArray(roles) && roles.includes('administrator');
}

/**
 * AuthWrapper component
 * Checks auth status on mount and shows login page if not authenticated
 */
export default function AuthWrapper({ children }: AuthWrapperProps) {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      // PUBLIC MODE: skip auth entirely
      if (PUBLIC_MODE) {
        setAuth({ status: 'authed', user: null });
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
          method: 'GET',
          credentials: 'include',
        });

        if (cancelled) return;

        if (res.ok) {
          const user = await res.json();
          setAuth({ status: 'authed', user });
        } else {
          setAuth({ status: 'unauthed' });
        }
      } catch (err) {
        console.error('[auth] Failed to check auth status:', err);
        if (!cancelled) {
          setAuth({ status: 'unauthed' });
        }
      }
    }

    checkAuth();

    return () => {
      cancelled = true;
    };
  }, []);

  // Presence tracking - keep SSE connection alive for online status
  // This runs when authenticated to track user as online
  useEffect(() => {
    if (auth.status !== 'authed') return;

    // Connect to SSE /all endpoint just for presence tracking
    const es = new EventSource(`${API_BASE}/sse/all`, { withCredentials: true });

    es.onerror = () => {
      // Silently handle errors - presence is best-effort
    };

    return () => {
      es.close();
    };
  }, [auth.status]);

  // Loading state
  if (auth.status === 'loading') {
    return (
      <div className="auth-loading">
        <p>Loading...</p>
        <style>{`
          .auth-loading {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #09090b;
            color: #94a3b8;
            font-family: system-ui, -apple-system, sans-serif;
          }
        `}</style>
      </div>
    );
  }

  // Show login page if not authenticated
  if (!PUBLIC_MODE && auth.status === 'unauthed') {
    return <LoginPage />;
  }

  // Authenticated - render children (the main App)
  return <>{children}</>;
}

/**
 * useAuth hook
 * Returns current auth state and user info
 */
export function useAuth() {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      if (PUBLIC_MODE) {
        setAuth({ status: 'authed', user: null });
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
          method: 'GET',
          credentials: 'include',
        });

        if (cancelled) return;

        if (res.ok) {
          const user = await res.json();
          setAuth({ status: 'authed', user });
        } else {
          setAuth({ status: 'unauthed' });
        }
      } catch {
        if (!cancelled) setAuth({ status: 'unauthed' });
      }
    }

    checkAuth();
    return () => { cancelled = true; };
  }, []);

  return {
    isLoading: auth.status === 'loading',
    isAuthenticated: auth.status === 'authed',
    user: auth.user,
    isAdmin: isAdmin(auth.user),
    logout: () => {
      window.location.href = `${API_BASE}/api/auth/logout?next=/`;
    },
  };
}
