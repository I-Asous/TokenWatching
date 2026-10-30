import { useEffect, useState } from "react";
import { useApi } from "../api";
import type { PromptActivity } from "../types";

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function History() {
  const api = useApi();
  const [records, setRecords] = useState<PromptActivity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    api("/prompt-w-optimized")
      .then((data: PromptActivity[]) => {
        if (active) {
          setRecords([...data].sort((a, b) =>
            new Date(b.org_prompt_input_time).getTime() - new Date(a.org_prompt_input_time).getTime(),
          ));
        }
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof Error ? error.message : "Could not load history.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [api]);

  return (
    <main className="Board1 history-page">
      <header className="history-heading">
        <h4>Conversation History</h4>
      </header>

      {isLoading && <p role="status">Loading history…</p>}
      {loadError && <p role="alert">Could not load history: {loadError}</p>}
      {!isLoading && !loadError && records.length === 0 && <p>No saved prompts yet.</p>}

      <section className="history-conversations" aria-label="Saved prompt conversations">
        {records.map((item, index) => (
          <details className="history-item" key={item.org_prompt_id}>
            <summary className="history-item-summary">
              <div className="history-item-header">
                <span>Conversation {records.length - index}</span>
                <time dateTime={item.org_prompt_input_time}>{formatDate(item.org_prompt_input_time)}</time>
              </div>
              <p className="history-preview">{item.org_prompt_txt}</p>
              <span className="history-expand-hint">Tap to view result</span>
            </summary>
            <div className="history-message history-result">
              <span className="history-message-label">
                {item.optimized_prompt_txt ? "Optimized prompt" : "Result"}
              </span>
              <p>{item.optimized_prompt_txt ?? item.org_prompt_txt}</p>
              {item.tokens_saved != null && <small>{item.tokens_saved} tokens saved</small>}
            </div>
          </details>
        ))}
      </section>
    </main>
  );
}
