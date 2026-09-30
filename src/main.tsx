import React from 'react';
import ReactDOM from 'react-dom/client';
import { ClerkProvider } from '@clerk/chrome-extension';
import App from './App';
import './style.css';

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const SYNC_HOST = import.meta.env.VITE_CLERK_SYNC_HOST;

if (!PUBLISHABLE_KEY) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY - add it to .env');
}

const indexUrl = chrome.runtime.getURL('index.html');

const clerkAppearance = {
  variables: {
    colorPrimary: '#E6D9E2',
    colorPrimaryForeground: '#4B3A30',
    colorBackground: '#85A08F',
    colorForeground: '#E6D9E2',
    colorMutedForeground: '#d7cfd3',
    colorInput: 'transparent',
    colorInputForeground: '#E6D9E2',
    colorBorder: '#E6D9E2',
    borderRadius: '10px',
    fontFamily: 'Arial, sans-serif',
    fontSize: '14px',
  },
  elements: {
    rootBox: { width: '100%' },
    cardBox: { width: '100%', margin: '0 auto', boxShadow: 'none', border: 'none' },
    card: {
      width: '100%',
      margin: '0 auto',
      boxShadow: 'none',
      border: 'none',
      backgroundColor: 'transparent',
    },
    footerAction: { display: 'none' },
    footer: { backgroundColor: 'transparent' },
    footerItem: { backgroundColor: 'transparent' },
    socialButtonsBlockButton: {
      backgroundColor: '#E6D9E2',
      borderColor: '#E6D9E2',
      color: '#4B3A30',
    },
    socialButtonsBlockButtonText: {
      color: '#4B3A30',
      fontWeight: 600,
    },
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY}
      syncHost={SYNC_HOST}
      afterSignOutUrl={indexUrl}
      signInFallbackRedirectUrl={indexUrl}
      signUpFallbackRedirectUrl={indexUrl}
      appearance={clerkAppearance}
    >
      <App />
    </ClerkProvider>
  </React.StrictMode>
);
