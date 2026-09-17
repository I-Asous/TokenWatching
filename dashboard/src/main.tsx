import {ClerkProvider, Show, SignInButton, SignUpButton, UserButton} from '@clerk/react';
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider afterSignOutUrl="/">
      <header style={{ display: "flex", height: "64px", alignItems: "center", justifyContent: "flex-end", gap: "16px", borderBottom: "1px solid #e5e7eb", padding: "0 16px" }}>
        <Show when="signed-out">
          <SignInButton />
          <SignUpButton />
        </Show>
        <Show when="signed-in">
          <UserButton />
        </Show>
      </header>
<App />
</ClerkProvider>
  </StrictMode>,
)