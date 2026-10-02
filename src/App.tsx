import { useState, type MouseEvent } from 'react';
import { Show, SignIn, SignUp, UserButton } from '@clerk/chrome-extension';
import Chatbox from './pages/Chatbox';
import History from './pages/History';
import Stats from './pages/Stats';
import Navbar, { type Tab } from './components/Navbar';

// Done with google login
const googleDone = new URLSearchParams(window.location.search).get('google') === 'done';
if (googleDone) {
  chrome.tabs.getCurrent(async (tab) => {
    if (!tab?.id) return;
    const [prev] = (await chrome.tabs.query({ windowId: tab.windowId, active: false })).sort((a, b) => (b.lastAccessed ?? 0) - (a.lastAccessed ?? 0));
    if (prev?.id) await chrome.tabs.update(prev.id, { active: true });
    await chrome.action.openPopup().catch(() => {});
    chrome.tabs.remove(tab.id);
  });
}

function App() {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const [tab, setTab] = useState<Tab>('prompt');
  if (googleDone) return null;

  // Open google login tab
  const openWebAppSignIn = (e: MouseEvent) => {
    if (!(e.target as HTMLElement).closest('.cl-socialButtonsBlockButton__google')) return;
    e.stopPropagation();
    chrome.tabs.create({ url: `${import.meta.env.VITE_CLERK_SYNC_HOST}/?google=1&ext=${chrome.runtime.id}` });
  };

  return (
    <>
      <div className="Logo">
        <h1>Token Watching</h1>
      </div>

      <Show when="signed-out">
        <div className="Board1" onClickCapture={openWebAppSignIn}>
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
        <Navbar active={tab} onChange={setTab} />

        {tab === 'stats' && <Stats />}
        {tab === 'prompt' && <Chatbox />}
        {tab === 'history' && <History />}

        <div className="Board1">
          <UserButton />
        </div>
      </Show>
    </>
  );
}

export default App;
