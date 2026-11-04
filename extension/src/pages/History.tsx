import { useEffect, useState } from "react";
import { useApi } from "../api";
import type { PromptActivity } from "../types";
import { loadPreferences } from "../settings";

type SavedValidation = {
  passed?: boolean;
  pass?: boolean;
  score: number;
  reasoning: string;
  react_trace?: string;
};

type RerunResult = {
  finalPrompt: string;
  wasOptimized: boolean;
  tokensSaved?: number;
  error?: string | null;
};

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function formatSavings(item: PromptActivity): string {
  const saved = item.tokens_saved ?? 0;
  const percent = (item.percent_saved ?? 0).toFixed(1);
  return `${saved} tokens saved · ${percent}% reduction`;
}

function promptSummary(item: PromptActivity): string {
  const compact = (item.optimized_prompt_txt ?? item.org_prompt_txt).replace(/\s+/g, " ").trim();
  const firstSentence = compact.split(/(?<=[.!?])\s+/)[0] || compact;
  return firstSentence.length > 100 ? `${firstSentence.slice(0, 97).trimEnd()}…` : firstSentence;
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
  const today = dateOnly(new Date());
  const targetDay = dateOnly(date);
  const dayOffset = Math.round((targetDay.getTime() - today.getTime()) / 86_400_000);
  const dateLabel = date.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  if (dayOffset === 0) return `Today · ${dateLabel}`;
  if (dayOffset === 1) return `Tomorrow · ${dateLabel}`;
  return dateLabel;
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
  const [selectedPrompt, setSelectedPrompt] = useState<PromptActivity | null>(null);
  const [openHistoryId, setOpenHistoryId] = useState<number | null>(null);
  const [savedValidations, setSavedValidations] = useState<SavedValidation[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const [reruns, setReruns] = useState<Record<number, { loading: boolean; result?: RerunResult; error?: string }>>({});
  const [copiedText, setCopiedText] = useState("");

  useEffect(() => {
    let active = true;
    function refreshHistory() {
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
    }

    refreshHistory();
    window.addEventListener("prompt-history-updated", refreshHistory);

    return () => {
      active = false;
      window.removeEventListener("prompt-history-updated", refreshHistory);
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

  async function openDetails(item: PromptActivity) {
    setSelectedPrompt(item);
    setSavedValidations([]);
    setDetailsError("");
    if (!item.optimized_prompt_id) {
      setDetailsError("No optimized prompt record is linked to this history entry, so validator details are unavailable.");
      return;
    }

    setDetailsLoading(true);
    try {
      const validations = await api(`/validations?optimized_prompt_id=${item.optimized_prompt_id}`) as SavedValidation[];
      setSavedValidations(validations ?? []);
    } catch (error) {
      setDetailsError(error instanceof Error ? error.message : "Could not load saved validator findings.");
    } finally {
      setDetailsLoading(false);
    }
  }

  async function rerunPrompt(item: PromptActivity) {
    setReruns((current) => ({ ...current, [item.org_prompt_id]: { loading: true } }));
    try {
      const preferences = await loadPreferences();
      const result = await api("/orchestrator", {
        method: "POST",
        body: JSON.stringify({
          prompt: item.org_prompt_txt,
          target: item.target || "chatgpt",
          validator_pass_score: preferences.validatorPassScore,
          max_optimization_attempts: preferences.maxOptimizationAttempts,
        }),
      }) as RerunResult;
      setReruns((current) => ({ ...current, [item.org_prompt_id]: { loading: false, result } }));
      window.dispatchEvent(new Event("prompt-history-updated"));
    } catch (error) {
      setReruns((current) => ({
        ...current,
        [item.org_prompt_id]: {
          loading: false,
          error: error instanceof Error ? error.message : "Could not rerun this prompt.",
        },
      }));
    }
  }

  async function copyText(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedText(label);
      window.setTimeout(() => setCopiedText((current) => current === label ? "" : current), 1800);
    } catch {
      setCopiedText(`failed-${label}`);
    }
  }

  if (selectedPrompt) {
    return (
      <main className="Board1 optimization-details">
        <button type="button" className="details-back-button" onClick={() => setSelectedPrompt(null)}>← Back to history</button>
        <h2>Prompt details</h2>
        <section className="details-section">
          <h3>Your prompt</h3>
          <p className="details-prompt">{selectedPrompt.org_prompt_txt}</p>
        </section>
        <section className="details-section">
          <h3>Auditor</h3>
          <p>Severity: {selectedPrompt.severity ?? "Not recorded"}</p>
          <p>Original prompt: {selectedPrompt.org_prompt_tokens ?? 0} tokens</p>
          <p>The existing History response includes severity and token count, but does not include the auditor’s issue descriptions.</p>
        </section>
        <section className="details-section">
          <h3>Optimizer</h3>
          <p>{selectedPrompt.tokens_saved ?? 0} tokens saved ({Number(selectedPrompt.percent_saved ?? 0).toFixed(1)}%)</p>
          <p>Token count: {selectedPrompt.org_prompt_tokens ?? 0} → {selectedPrompt.optimized_prompt_tokens ?? selectedPrompt.org_prompt_tokens ?? 0}</p>
          <p>The saved optimized prompt is shown below. The existing History data doesn’t include the optimizer’s edit summary.</p>
        </section>
        <section className="details-section">
          <h3>Validator</h3>
          {savedValidations.length ? savedValidations.map((validation, index) => (
            <div className="details-attempt" key={index}>
              <strong>{(validation.passed ?? validation.pass) ? "Passed" : "Did not pass"}</strong>
              <p>Quality score: {validation.score}/10</p>
              <p>{validation.reasoning}</p>
              {validation.react_trace ? <details><summary>Full validation review</summary><p className="details-prompt">{validation.react_trace}</p></details> : null}
            </div>
          )) : <p>No saved validation findings were found.</p>}
          {detailsLoading && <p role="status">Loading validation findings…</p>}
          {detailsError && <p role="alert">{detailsError}</p>}
        </section>
        <section className="details-section">
          <h3>Saved result</h3>
          <p className="details-prompt">{selectedPrompt.optimized_prompt_txt ?? selectedPrompt.org_prompt_txt}</p>
        </section>
      </main>
    );
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
                {day.entries.map(({ item }) => (
                  <details
                    className={item.optimized_prompt_txt ? "history-item history-item-optimized" : "history-item history-item-original"}
                    key={item.org_prompt_id}
                    open={openHistoryId === item.org_prompt_id}
                    onToggle={(event) => {
                      if (event.currentTarget.open && openHistoryId !== item.org_prompt_id) {
                        setOpenHistoryId(item.org_prompt_id);
                      } else if (!event.currentTarget.open && openHistoryId === item.org_prompt_id) {
                        setOpenHistoryId(null);
                      }
                    }}
                  >
                    <summary className="history-item-summary">
                      <div className="history-item-header">
                        <time dateTime={item.org_prompt_input_time}>{formatDate(item.org_prompt_input_time)}</time>
                      </div>
                      <span className="history-token-count">{formatSavings(item)}</span>
                      <p className={`history-preview ${item.optimized_prompt_txt ? "history-optimized-preview" : "history-unoptimized-preview"}`}>
                        {promptSummary(item)}
                      </p>
                      <span className="history-expand-hint">Tap to view full result and original prompt</span>
                    </summary>
                    <div className="history-expanded-content">
                      <details className="history-full-optimized">
                        <summary>View full optimized prompt</summary>
                        <p>{item.optimized_prompt_txt ?? item.org_prompt_txt}</p>
                      </details>
                      <div className="history-actions">
                        <button type="button" className="history-action-button" onClick={() => void copyText(item.org_prompt_txt, `original-${item.org_prompt_id}`)}>
                          Copy original
                        </button>
                        <button type="button" className="history-action-button" onClick={() => void copyText(item.optimized_prompt_txt ?? item.org_prompt_txt, `result-${item.org_prompt_id}`)}>
                          Copy result
                        </button>
                        <button
                          type="button"
                          className="history-action-button history-rerun-button"
                          onClick={() => void rerunPrompt(item)}
                          disabled={reruns[item.org_prompt_id]?.loading}
                        >
                          {reruns[item.org_prompt_id]?.loading ? "Rerunning…" : "Rerun optimization"}
                        </button>
                      </div>
                      {copiedText.startsWith(`original-${item.org_prompt_id}`) && <small role="status">Original prompt copied.</small>}
                      {copiedText.startsWith(`result-${item.org_prompt_id}`) && <small role="status">Result copied.</small>}
                      {(copiedText === `failed-original-${item.org_prompt_id}` || copiedText === `failed-result-${item.org_prompt_id}`) && <small role="alert">Copy failed. Allow clipboard access and try again.</small>}
                      {reruns[item.org_prompt_id]?.error && <p className="history-action-error" role="alert">{reruns[item.org_prompt_id].error}</p>}
                      {reruns[item.org_prompt_id]?.result && (
                        <div className="history-rerun-result">
                          <span className="history-message-label">New optimization result</span>
                          <p>{reruns[item.org_prompt_id].result?.finalPrompt}</p>
                          <small>
                            {reruns[item.org_prompt_id].result?.wasOptimized
                              ? `${reruns[item.org_prompt_id].result?.tokensSaved ?? 0} tokens saved`
                              : reruns[item.org_prompt_id].result?.error ?? "Original prompt kept."}
                          </small>
                          <button type="button" className="history-action-button" onClick={() => void copyText(reruns[item.org_prompt_id].result?.finalPrompt ?? "", `rerun-${item.org_prompt_id}`)}>
                            Copy new result
                          </button>
                          {copiedText === `rerun-${item.org_prompt_id}` && <small role="status">New result copied.</small>}
                          {copiedText === `failed-rerun-${item.org_prompt_id}` && <small role="alert">Copy failed. Allow clipboard access and try again.</small>}
                        </div>
                      )}
                      <button type="button" className="view-details-button" onClick={() => void openDetails(item)}>
                        View details
                      </button>
                      <div className="history-original-prompt">
                        <span className="history-message-label">Original prompt</span>
                        <p>{item.org_prompt_txt}</p>
                        <small>{item.org_prompt_tokens ?? 0} tokens before optimization</small>
                      </div>
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
