import { useState } from 'react';
import { Show, SignIn, SignUp, UserButton } from '@clerk/chrome-extension';

function App() {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');

  return (
    <>
      <div className="Logo">
        <h1>Token Watching</h1>
      </div>

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
