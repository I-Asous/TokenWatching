import { useEffect, useState } from "react";
import { useApi } from "../api";

type ChatTurn = {
  id: number;
  prompt: string;
  result: string | null;
  status: "processing" | "complete" | "error";
  wasOptimized: boolean | null;
};

type OrchestrationResponse = {
  finalPrompt: string;
  wasOptimized: boolean;
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
      { id: turnId, prompt: txtPrompt, result: null, status: "processing", wasOptimized: null },
    ]);

    try {
      const result = await api("/orchestrator", {
        method: "POST",
        body: JSON.stringify({ prompt: txtPrompt, target: "chatgpt" }),
      }) as OrchestrationResponse;

      setTurns((previousTurns) => previousTurns.map((turn) =>
        turn.id === turnId
          ? { ...turn, result: result.finalPrompt, status: "complete", wasOptimized: result.wasOptimized }
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
                      {turn.wasOptimized ? "Optimized prompt" : "No optimization was needed"}
                    </small>
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
