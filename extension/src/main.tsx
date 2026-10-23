import React from 'react';
import ReactDOM from 'react-dom/client';
import { ClerkProvider } from '@clerk/chrome-extension';
import App from './App';
import './style.css';

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!PUBLISHABLE_KEY) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY - add it to .env');
}

const indexUrl = chrome.runtime.getURL('index.html');

const clerkAppearance = {
  variables: {
    colorPrimary: '#000000',
    colorPrimaryForeground: '#FFFFFF',
    colorBackground: '#FFFFFF',
    colorForeground: '#000000',
    colorMutedForeground: '#333333',
    colorInput: '#FFFFFF',
    colorInputForeground: '#000000',
    colorBorder: '#000000',
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
      backgroundColor: '#000000',
      borderColor: '#000000',
      color: '#FFFFFF',
    },
    socialButtonsBlockButtonText: {
      color: '#FFFFFF',
      fontWeight: 600,
    },
  },
};


ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY}
      afterSignOutUrl={indexUrl}
      signInFallbackRedirectUrl={indexUrl}
      signUpFallbackRedirectUrl={indexUrl}
      appearance={clerkAppearance}
    >
      <App />
    </ClerkProvider>
  </React.StrictMode>
);
