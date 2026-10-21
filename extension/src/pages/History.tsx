export default function History() {
  return (
    <main className="Board1 history-page">
      <header className="history-heading">
        <h4>Conversation History</h4>
        <p>Your saved prompts and results will appear here.</p>
      </header>

      <section className="history-chat" aria-label="Saved prompt conversations">
        <div className="history-empty-icon" aria-hidden="true">↺</div>
        <strong>No saved conversations yet</strong>
        <p>Save a prompt from the Prompt tab to start building your history.</p>
      </section>
    </main>
  );
}
