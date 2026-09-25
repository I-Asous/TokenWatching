import { Show, SignIn, UserButton } from '@clerk/chrome-extension';

function App() {
  return (
    <>
      <div className="Logo">
        <h1>Token Watching</h1>
      </div>

      <Show when="signed-out">
        <div className="Board1">
          <SignIn />
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
