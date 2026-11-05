import { useEffect, useState } from "react";
import { useApi } from "../api";

type ChatTurn = {
  id: number;
  prompt: string;
  result: string | null;
  status: "processing" | "complete" | "error";
  wasOptimized: boolean | null;
  optimizationMessage: string | null;
  // the quick result came back and the LLM pass could still improve it
  canOptimizeFurther: boolean;
  // the "Optimize further" request is running
  optimizingFurther: boolean;
};

type OrchestrationResponse = {
  finalPrompt: string;
  wasOptimized: boolean;
  error?: string | null;
  attempts?: Array<{ passed: boolean }>;
  canOptimizeFurther?: boolean;
};

// What to show under a result that wasn't optimized
function optimizationMessage(result: OrchestrationResponse) {
  if (result.error) return `Optimization failed: ${result.error}`;
  if (result.canOptimizeFurther) return "No quick fixes found.";
  if (result.attempts?.length) return "No rewrite passed validation; original returned.";
  return "Original returned unchanged (no changes needed or no token savings).";
}

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
      {
        id: turnId, prompt: txtPrompt, result: null, status: "processing", wasOptimized: null,
        optimizationMessage: null, canOptimizeFurther: false, optimizingFurther: false,
      },
    ]);

    try {
      const result = await api("/orchestrator", {
        method: "POST",
        body: JSON.stringify({ prompt: txtPrompt, target: "chatgpt" }),
      }) as OrchestrationResponse;

      setTurns((previousTurns) => previousTurns.map((turn) =>
        turn.id === turnId
          ? {
              ...turn,
              result: result.finalPrompt,
              status: "complete",
              wasOptimized: result.wasOptimized,
              optimizationMessage: optimizationMessage(result),
              canOptimizeFurther: Boolean(result.canOptimizeFurther),
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

  // Runs the LLM pass (Optimizer + Validator) on a turn's original prompt and replaces its quick result.
  // If it fails, the quick result stays and the error is shown
  async function optimizeFurther(turnId: number, txtPrompt: string) {
    setSendError("");
    setTurns((previousTurns) => previousTurns.map((turn) =>
      turn.id === turnId ? { ...turn, optimizingFurther: true } : turn,
    ));

    try {
      const result = await api("/orchestrator", {
        method: "POST",
        body: JSON.stringify({ prompt: txtPrompt, target: "chatgpt", optimizeFurther: true }),
      }) as OrchestrationResponse;

      setTurns((previousTurns) => previousTurns.map((turn) =>
        turn.id !== turnId
          ? turn
          // a full pass that found nothing better keeps the quick rewrite instead of going back to the original
          : !result.wasOptimized && turn.wasOptimized
            ? { ...turn, canOptimizeFurther: false, optimizingFurther: false }
            : {
                ...turn,
                result: result.finalPrompt,
                wasOptimized: result.wasOptimized,
                optimizationMessage: optimizationMessage(result),
                canOptimizeFurther: false,
                optimizingFurther: false,
              },
      ));
    } catch (error) {
      setSendError(error instanceof Error ? error.message : "Could not reach the backend");
      setTurns((previousTurns) => previousTurns.map((turn) =>
        turn.id === turnId ? { ...turn, optimizingFurther: false } : turn,
      ));
    }
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
                    {turn.canOptimizeFurther && (
                      <button
                        type="button"
                        className="optimize-further-button"
                        onClick={() => optimizeFurther(turn.id, turn.prompt)}
                        disabled={turn.optimizingFurther}
                      >
                        {turn.optimizingFurther ? "Optimizing…" : "Optimize further"}
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
