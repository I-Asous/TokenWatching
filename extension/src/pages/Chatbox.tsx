import { useState, useEffect } from 'react';

type ChatTurn = {
  id: number;
  prompt: string;
  result: string | null;
};

const promptExamples = [
  "Write a polite email asking my manager to move our meeting to tomorrow.",
  "Explain photosynthesis in simple terms for a middle school student.",
  "Help me plan a quick dinner using rice, vegetables, and eggs.",
  "Summarize these notes into three clear action items.",
];

function Chatbox() {
  const [promptValue, setPromptValue] = useState("");
  const [promptExampleIndex, setPromptExampleIndex] = useState(0);
  const [showPromptExample, setShowPromptExample] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [sendMessage, setSendMessage] = useState("");
  const [sendError, setSendError] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);

  useEffect(() => {
    // 1. Find the active tab when Chatbox loads
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const activeTab = tabs[0];
      
      if (activeTab?.id) {
        // 2. Ask the content script for ChatGPT's prompt text
        chrome.tabs.sendMessage(
          activeTab.id, 
          { action: "get_chatgpt_text" }, 
          (response) => {
            // 3. Put the response into extension
            if (response && response.promptText) {
              setPromptValue(response.promptText);
            }
          }
        );
      }
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

    try {
      const apiBaseUrl = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
      const response = await fetch(`${apiBaseUrl}/prompts/guest-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          txt_prompt: txtPrompt,
        }),
      });
      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(result.detail ?? `Backend request failed (${response.status}).`);
      }

      setTurns((previousTurns) => [
        ...previousTurns,
        {
          id: Date.now(),
          prompt: txtPrompt,
          result: null,
        },
      ]);
      setPromptValue("");
      setSendMessage("Prompt saved. Optimization results are not connected yet.");
    } catch (error) {
      setSendError(
        error instanceof Error
          ? error.message
          : "Could not reach the backend",
      );
    } finally {
      setIsSending(false);
    }
  }
  return (
    <div>
      <div className="Board1">
        <h4 className="enter">Enter Prompt</h4>

        {}

        <div className="chat-history">
  {turns.map((turn) => (
    <div className="chat-turn" key={turn.id}>
      <div className="chat-message user-message">
<span className="message-label">You</span>
    <p>{turn.prompt}</p>
  </div>

  <div className="chat-message result-message">
    <span className="message-label">Result</span>
    <p>{turn.result ?? "No optimized result yet."}</p>

      </div>
    </div>
  ))}
</div>

        <div className="prompt-input-wrap">
          <textarea
            className="promptext"
            value={promptValue}
            aria-label="Enter a prompt"
            onChange={(e) => setPromptValue(e.target.value)}
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
