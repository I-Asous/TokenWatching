import { useAuth } from '@clerk/chrome-extension';
import { useCallback } from 'react';

export function useApi() {
  const { getToken } = useAuth();

  return useCallback(async (path: string, init: RequestInit = {}) => {
    const token = await getToken();
    const apiBaseUrl = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
    const res = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: { ...init.headers, 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null) as { detail?: string } | null;
      throw new Error(body?.detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  }, [getToken]);
}
