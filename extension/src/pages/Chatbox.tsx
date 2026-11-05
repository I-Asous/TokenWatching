import { useEffect, useState } from "react";
import { useApi } from "../api";
import { loadPreferences } from "../settings";

type ChatTurn = {
  id: number;
  prompt: string;
  result: string | null;
  status: "processing" | "complete" | "error";
  wasOptimized: boolean | null;
  optimizationMessage: string | null;
  details: OrchestrationResponse | null;
};

type OptimizationAttempt = {
  originalTokens: number;
  optimizedTokens: number;
  tokensSaved: number;
  percentSaved: number;
  optimizedPrompt: string;
  changes?: string[];
  preservedConstraints?: string[];
};

type ValidationAttempt = {
  passed: boolean;
  qualityScore: number;
  reasoning: string;
  reactTrace?: string;
};

type OrchestrationResponse = {
  finalPrompt: string;
  wasOptimized: boolean;
  error?: string | null;
  tokensSaved?: number;
  percentSaved?: number;
  changes?: string[];
  promptTypes?: string[];
  auditResult?: { issues?: string[]; severity?: string; token_count?: number };
  optimizerAttempts?: OptimizationAttempt[];
  attempts?: ValidationAttempt[];
};

const promptExamples = [
  "Write a polite email asking my manager to move our meeting to tomorrow.",
  "Explain photosynthesis in simple terms for a middle school student.",
  "Help me plan a quick dinner using rice, vegetables, and eggs.",
  "Summarize these notes into three clear action items.",
];

function Chatbox() {
  const api = useApi();
  const [promptValue, setPromptValue] = useState("");
  const [promptExampleIndex, setPromptExampleIndex] = useState(0);
  const [showPromptExample, setShowPromptExample] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [sendMessage, setSendMessage] = useState("");
  const [sendError, setSendError] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [selectedDetails, setSelectedDetails] = useState<ChatTurn | null>(null);

  useEffect(() => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const activeTab = tabs[0];
      if (!activeTab?.id) return;

      chrome.tabs.sendMessage(activeTab.id, { action: "get_chatgpt_text" }, (response) => {
        if (response?.promptText) setPromptValue(response.promptText);
      });
    });
  }, []);

  useEffect(() => {
    if (promptValue) {
      setShowPromptExample(false);
      return;
    }

    setShowPromptExample(true);
    let transitionTimer: number | undefined;
    const cycleTimer = window.setInterval(() => {
      setShowPromptExample(false);
      transitionTimer = window.setTimeout(() => {
        setPromptExampleIndex((index) => (index + 1) % promptExamples.length);
        setShowPromptExample(true);
      }, 300);
    }, 3600);

    return () => {
      window.clearInterval(cycleTimer);
      if (transitionTimer !== undefined) window.clearTimeout(transitionTimer);
    };
  }, [promptValue]);

  async function sendPrompt() {
    const txtPrompt = promptValue.trim();
    if (!txtPrompt) {
      setSendError("Enter a prompt first.");
      setSendMessage("");
      return;
    }

    setIsSending(true);
    setSendError("");
    setSendMessage("");
    const turnId = Date.now();
    setTurns((previousTurns) => [
      ...previousTurns,
      { id: turnId, prompt: txtPrompt, result: null, status: "processing", wasOptimized: null, optimizationMessage: null, details: null },
    ]);

    try {
      const preferences = await loadPreferences();
      const result = await api("/orchestrator", {
        method: "POST",
        body: JSON.stringify({
          prompt: txtPrompt,
          target: "chatgpt",
          validator_pass_score: preferences.validatorPassScore,
          max_optimization_attempts: preferences.maxOptimizationAttempts,
        }),
      }) as OrchestrationResponse;
      window.dispatchEvent(new Event("prompt-history-updated"));

      setTurns((previousTurns) => previousTurns.map((turn) =>
        turn.id === turnId
          ? {
              ...turn,
              result: result.finalPrompt,
              status: "complete",
              wasOptimized: result.wasOptimized,
              details: result,
              optimizationMessage: result.error
                ? `Optimization failed: ${result.error}`
                : result.attempts?.length
                  ? `No rewrite passed validation. ${result.attempts.map((attempt) => attempt.reasoning).filter(Boolean).join(" ")}`
                  : result.auditResult?.issues?.length
                    ? "No shorter rewrite saved tokens, so the original was kept."
                    : "The audit found no token-saving issues, so the original was kept.",
            }
          : turn,
      ));
      setPromptValue("");
      setSendMessage("Result ready.");
    } catch (error) {
      setSendError(error instanceof Error ? error.message : "Could not reach the backend");
      setTurns((previousTurns) => previousTurns.map((turn) =>
        turn.id === turnId ? { ...turn, status: "error" } : turn,
      ));
    } finally {
      setIsSending(false);
    }
  }

  if (selectedDetails?.details) {
    const { details } = selectedDetails;
    const optimizerAttempts = details.optimizerAttempts ?? [];
    const validationAttempts = details.attempts ?? [];

    return (
      <div className="Board1 optimization-details">
        <button type="button" className="details-back-button" onClick={() => setSelectedDetails(null)}>
          ← Back to chat
        </button>
        <h2>Prompt details</h2>
        <section className="details-section">
          <h3>Your prompt</h3>
          <p className="details-prompt">{selectedDetails.prompt}</p>
        </section>

        <section className="details-section">
          <h3>Auditor</h3>
          <p>Severity: {details.auditResult?.severity ?? "Not reported"}</p>
          {typeof details.auditResult?.token_count === "number" && <p>Original tokens: {details.auditResult.token_count}</p>}
          {details.auditResult?.issues?.length ? (
            <ul>{details.auditResult.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul>
          ) : <p>No token-saving issues were found.</p>}
        </section>

        <section className="details-section">
          <h3>Optimizer</h3>
          {optimizerAttempts.length ? optimizerAttempts.map((attempt, index) => (
            <div className="details-attempt" key={index}>
              <strong>Candidate {index + 1}</strong>
              <p>{attempt.tokensSaved > 0 ? `${attempt.tokensSaved} tokens saved (${Math.round(attempt.percentSaved)}%)` : "No tokens saved"}</p>
              <p>{attempt.originalTokens} → {attempt.optimizedTokens} tokens</p>
              {attempt.changes?.length ? <><strong>Changes</strong><ul>{attempt.changes.map((change, changeIndex) => <li key={changeIndex}>{change}</li>)}</ul></> : <p>No wording changes proposed.</p>}
              {attempt.preservedConstraints?.length ? <><strong>Requirements preserved</strong><ul>{attempt.preservedConstraints.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></> : null}
              <details><summary>Candidate prompt</summary><p className="details-prompt">{attempt.optimizedPrompt}</p></details>
            </div>
          )) : <p>The optimizer did not run because the audit found no issues or this prompt type skips optimization.</p>}
          {details.promptTypes?.length ? <p>Prompt type: {details.promptTypes.join(", ")}</p> : null}
        </section>

        <section className="details-section">
          <h3>Validator</h3>
          {validationAttempts.length ? validationAttempts.map((attempt, index) => (
            <div className="details-attempt" key={index}>
              <strong>Candidate {index + 1}: {attempt.passed ? "Passed" : "Did not pass"}</strong>
              <p>Quality score: {attempt.qualityScore}/10</p>
              <p>{attempt.reasoning}</p>
              {attempt.reactTrace ? <details><summary>Full validation review</summary><p className="details-prompt">{attempt.reactTrace}</p></details> : null}
            </div>
          )) : <p>The validator did not run because no candidate needed validation.</p>}
          {details.error ? <p role="alert">{details.error}</p> : null}
        </section>
        <section className="details-section">
          <h3>Result</h3>
          <p>{details.wasOptimized ? "Optimized prompt accepted." : "Original prompt kept."}</p>
          <p className="details-prompt">{details.finalPrompt}</p>
        </section>
      </div>
    );
  }

  return (
    <div>
      <div className="Board1">
        <h4 className="enter">Enter Prompt</h4>

        <div className="chat-history">
          {turns.map((turn) => (
            <div className="chat-turn" key={turn.id}>
              <div className="chat-message user-message">
                <span className="message-label">You</span>
                <p>{turn.prompt}</p>
              </div>
              <div className="chat-message result-message">
                <span className="message-label">Result</span>
                {turn.status === "processing" && <p>Working on your prompt…</p>}
                {turn.status === "error" && <p>Could not generate a result. You can try again.</p>}
                {turn.status === "complete" && (
                  <>
                    <p>{turn.result}</p>
                    <small>
                      {turn.wasOptimized
                        ? "Optimized prompt"
                        : turn.optimizationMessage}
                    </small>
                    {turn.details && (
                      <button type="button" className="view-details-button" onClick={() => setSelectedDetails(turn)}>
                        View details
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="prompt-input-wrap">
          <textarea
            className="promptext"
            value={promptValue}
            aria-label="Enter a prompt"
            onChange={(event) => setPromptValue(event.target.value)}
          />
          {!promptValue && (
            <div
              className={`prompt-example${showPromptExample ? "" : " is-fading"}`}
              aria-hidden="true"
            >
              {promptExamples[promptExampleIndex]}
            </div>
          )}
          <button
            type="button"
            className="prompt-send-button"
            onClick={sendPrompt}
            disabled={isSending}
            aria-label={isSending ? "Sending prompt" : "Send prompt"}
            title={isSending ? "Sending..." : "Send prompt"}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        {sendMessage && <p role="status">{sendMessage}</p>}
        {sendError && <p role="alert">{sendError}</p>}
      </div>
    </div>
  );
}

export default Chatbox;
