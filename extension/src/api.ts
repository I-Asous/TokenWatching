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

// websockets
export function useOrchestrator() {
  const { getToken } = useAuth();

  return useCallback(async (body: object, onStage: (stage: string) => void) => {
    const token = await getToken();
    if (!token) throw new Error('Sign in to optimize prompts.');
    const apiBaseUrl = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
    const ws = new WebSocket(`${apiBaseUrl.replace(/^http/, 'ws')}/orchestrator/ws`);

    return new Promise((resolve, reject) => {
      ws.onopen = () => ws.send(JSON.stringify({ ...body, token }));
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.stage === 'done') resolve(message.result);
        else if (message.stage === 'failed') reject(new Error('Optimization failed, try again.'));
        else onStage(message.stage);
      };
      // close after result
      ws.onclose = () => reject(new Error('Lost connection to the backend.'));
    });
  }, [getToken]);
}
