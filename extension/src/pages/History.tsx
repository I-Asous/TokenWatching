import { useEffect, useState } from "react";
import { useApi } from "../api";
import type { PromptActivity } from "../types";

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function dateOnly(value: string): Date {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
}

function dateId(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function formatDay(date: Date): string {
  return date.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function formatWeek(start: Date): string {
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const startLabel = start.toLocaleDateString([], { month: "short", day: "numeric" });
  const endLabel = end.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  return `Week of ${startLabel} – ${endLabel}`;
}

export default function History() {
  const api = useApi();
  const [records, setRecords] = useState<PromptActivity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

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

  async function deleteHistory() {
    if (isDeleting || records.length === 0) return;
    if (!window.confirm("Delete all saved conversation history? This cannot be undone.")) return;

    setIsDeleting(true);
    setDeleteError("");
    const deletedIds = new Set<number>();
    let failed = false;
    for (const item of records) {
      try {
        await api(`/prompts/${item.org_prompt_id}`, { method: "DELETE" });
        deletedIds.add(item.org_prompt_id);
      } catch {
        failed = true;
      }
    }
    setRecords((current) => current.filter((item) => !deletedIds.has(item.org_prompt_id)));
    if (failed) setDeleteError("Some conversations could not be deleted. Please try again.");
    setIsDeleting(false);
  }

  const weeks = new Map<string, { start: Date; days: Map<string, { date: Date; entries: Array<{ item: PromptActivity; index: number }> }> }>();
  records.forEach((item, index) => {
    const date = dateOnly(item.org_prompt_input_time);
    if (Number.isNaN(date.getTime())) return;
    const weekStart = new Date(date);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const weekKey = dateId(weekStart);
    let week = weeks.get(weekKey);
    if (!week) {
      week = { start: weekStart, days: new Map() };
      weeks.set(weekKey, week);
    }
    const dayKey = dateId(date);
    let day = week.days.get(dayKey);
    if (!day) {
      day = { date, entries: [] };
      week.days.set(dayKey, day);
    }
    day.entries.push({ item, index });
  });

  return (
    <main className="Board1 history-page">
      <header className="history-heading">
        <h4>Conversation History</h4>
        {records.length > 0 && (
          <button className="history-delete-button" type="button" onClick={deleteHistory} disabled={isDeleting}>
            {isDeleting ? "Deleting…" : "Delete history"}
          </button>
        )}
      </header>

      {isLoading && <p role="status">Loading history…</p>}
      {loadError && <p role="alert">Could not load history: {loadError}</p>}
      {deleteError && <p role="alert">{deleteError}</p>}
      {!isLoading && !loadError && records.length === 0 && <p>No saved prompts yet.</p>}

      <section className="history-conversations" aria-label="Saved prompt conversations">
        {[...weeks.entries()].map(([weekKey, week]) => (
          <section className="history-week" key={weekKey}>
            <h5 className="history-week-heading">{formatWeek(week.start)}</h5>
            {[...week.days.entries()].map(([dayKey, day]) => (
              <section className="history-day" key={dayKey}>
                <h6 className="history-day-heading">{formatDay(day.date)}</h6>
                {day.entries.map(({ item, index }) => (
                  <details className="history-item" key={item.org_prompt_id}>
                    <summary className="history-item-summary">
                      <div className="history-item-header">
                        <span>Conversation {records.length - index}</span>
                        <time dateTime={item.org_prompt_input_time}>{formatDate(item.org_prompt_input_time)}</time>
                      </div>
                      <span className="history-token-count">{item.tokens_saved ?? 0} tokens saved</span>
                      <p className="history-preview">{item.org_prompt_txt}</p>
                      <span className="history-expand-hint">Tap to view result</span>
                    </summary>
                    <div className="history-message history-result">
                      <span className="history-message-label">
                        {item.optimized_prompt_txt ? "Optimized prompt" : "Result"}
                      </span>
                      <p>{item.optimized_prompt_txt ?? item.org_prompt_txt}</p>
                      <small>{item.tokens_saved ?? 0} tokens saved</small>
                    </div>
                  </details>
                ))}
              </section>
            ))}
          </section>
        ))}
      </section>
    </main>
  );
}
