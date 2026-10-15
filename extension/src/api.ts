import { useAuth } from '@clerk/chrome-extension';

export function useApi() {
  const { getToken } = useAuth();

  return async (path: string, init: RequestInit = {}) => {
    const token = await getToken();
    const res = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
      ...init,
      headers: { ...init.headers, 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  };
}
