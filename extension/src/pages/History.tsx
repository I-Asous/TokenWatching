type HistoryItem = {
  id: number;
  time: string;
  prompt: string;
  result: string;
};

const sampleHistory: HistoryItem[] = [
  {
    id: 1,
    time: "Today · 10:42 AM",
    prompt: "Write a polite email asking my manager to move our meeting to tomorrow.",
    result: "Write email asking manager to move meeting to tomorrow",
  },
  {
    id: 2,
    time: "Yesterday · 3:18 PM",
    prompt: "Explain photosynthesis in simple terms for a middle school student.",
    result: "Explain photosynthesis in simple terms",
  },
];

export default function History() {
  return (
    <main className="Board1 history-page">
      <header className="history-heading">
        <h4>Conversation History</h4>
      </header>

      <section className="history-conversations" aria-label="Sample saved prompt conversations">
        {sampleHistory.map((item) => (
          <details className="history-item" key={item.id}>
            <summary className="history-item-summary">
            <div className="history-item-header">
              <span>Conversation {item.id}</span>
              <time>{item.time}</time>
            </div>
              <p className="history-preview">{item.prompt}</p>
              <span className="history-expand-hint">Tap to view result</span>
            </summary>
            <div className="history-message history-result">
              <span className="history-message-label">Result</span>
              <p>{item.result}</p>
            </div>
          </details>
        ))}
      </section>
    </main>
  );
}
