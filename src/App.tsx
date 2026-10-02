import { useState } from 'react';
import Chatbox from './pages/Chatbox';
import History from './pages/History';
import Stats from './pages/Stats';
import Navbar, { type Tab } from './components/Navbar';
import { Show, SignIn, SignUp, UserButton } from '@clerk/chrome-extension';

function App() {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const [tab, setTab] = useState<Tab>('prompt');

  return (
    <>
      <div className="Logo">
        <h1>Token Watching</h1>
      </div>
    
      <Navbar active={tab} onChange={setTab} />

      {tab === 'stats' && <Stats />}
      {tab === 'prompt' && <Chatbox />}
      {tab === 'history' && <History />}
      <Show when="signed-out">
        <div className="Board1">
          {mode === 'sign-in' ? <SignIn routing="hash" /> : <SignUp routing="hash" />}

          <div className="buttons">
            {mode === 'sign-in' ? (
              <button type="button" className="app-button" onClick={() => setMode('sign-up')}>
                Sign up instead
              </button>
            ) : (
              <button type="button" className="app-button" onClick={() => setMode('sign-in')}>
                Sign in instead
              </button>
            )}
          </div>
        </div>
      </Show>

      <Show when="signed-in">
        <div className="Board1">
          <UserButton />
        </div>
      </Show>
    </>
  );
}

export default App;
