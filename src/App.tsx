function App() {
  return (
    <>
    <div className="Logo">
      <h1>Token Watching</h1>
      </div>

      <div className="Board1">
      
      <h2>Login</h2>

      <div className="input-login">
      


        <div className="container">
          <input type="text" name="username-id" placeholder=" " />
          <div className="lableLine"> Username </div>
          </div>
          
          <div className="container">
          <input type="text" name="password-id" placeholder=" " />
          <div className="lableLine"> Password </div>
          </div>
          
      </div>

      <div className="buttons">
        <button>Login</button>
        <button>Signup</button>
      </div>
        <a href="">forgot passoword</a>
    </div>
    </>
  );
}

export default App;