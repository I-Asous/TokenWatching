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
        <p>Review prompts and their results.</p>
      </header>

      <div className="history-sample-note">Sample conversations · preview only</div>

      <section className="history-conversations" aria-label="Sample saved prompt conversations">
        {sampleHistory.map((item) => (
          <article className="history-item" key={item.id}>
            <div className="history-item-header">
              <span>Conversation {item.id}</span>
              <time>{item.time}</time>
            </div>
            <div className="history-message history-prompt">
              <span className="history-message-label">You</span>
              <p>{item.prompt}</p>
            </div>
            <div className="history-message history-result">
              <span className="history-message-label">Result</span>
              <p>{item.result}</p>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
