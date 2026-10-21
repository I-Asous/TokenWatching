import { useState, useEffect } from 'react';

type ChatTurn = {
  id: number;
  prompt: string;
  result: string | null;
};

function Chatbox() {
  const [promptValue, setPromptValue] = useState("");
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

        <textarea 
          className="promptext"
          value={promptValue}
          placeholder='Ex: Write me an email telling my boss that Ill be late to work due to an emergency at work'
          onChange={(e) => setPromptValue(e.target.value)}
        />
        <div className="buttons">
          <button
            type="button"
            className="app-button"
            onClick={sendPrompt}
            disabled={isSending}
          >
            {isSending ? "Sending..." : "Send prompt"}
          </button>
        </div>
        {sendMessage && <p role="status">{sendMessage}</p>}
        {sendError && <p role="alert">{sendError}</p>}
      </div>
    </div>
  );
}

export default Chatbox;
