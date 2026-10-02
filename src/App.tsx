import { useState } from 'react';
import Login from './pages/Login';
import Chatbox from './pages/Chatbox';
import History from './pages/History';
import Stats from './pages/Stats';
import Navbar, { type Tab } from './components/Navbar';


function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [tab, setTab] = useState<Tab>('prompt');

  if (!loggedIn) {
    return <Login onLogin={() => setLoggedIn(true)} />;
  }

  return (
    <>
      <div className="Logo">
        <h1>Token Watching</h1>
      </div>

      <Navbar active={tab} onChange={setTab} />

      {tab === 'stats' && <Stats />}
      {tab === 'prompt' && <Chatbox />}
      {tab === 'history' && <History />}
    </>
  );
}

export default App;