import { useState, useEffect } from 'react';

// websocket stage messages
const STAGE_MESSAGES: Record<string, string> = {
  auditing: "Calculating Cost...",
  optimizing: "Cleaning Up...",
  validating: "Double Checking...",
  done: "Done!",
};

function Chatbox() {
  const [promptValue, setPromptValue] = useState("");
  const [stage, setStage] = useState("");
  const [sendError, setSendError] = useState("");

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

  // MOCK: connects to the backend and shows each stage it sends back
  function sendPrompt() {
    if (!promptValue.trim()) {
      setSendError("Enter a prompt first.");
      return;
    }
    setSendError("");

    const ws = new WebSocket(`${import.meta.env.VITE_API_URL.replace(/^http/, "ws")}/ws`);
    ws.onmessage = (event) => setStage(JSON.parse(event.data).stage);
    ws.onerror = () => setSendError("Could not reach the backend");
  }

  return (
    <div>
      <div className="Board1">
        <h4 className="enter">Enter Prompt</h4>

        {}
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
          >
            test
          </button>
        </div>
        {stage && (
          <div className="progress" role="status">
            {stage !== "done" && <span className="spinner" />}
            {STAGE_MESSAGES[stage]}
          </div>
        )}
        {sendError && <p role="alert">{sendError}</p>}
      </div>
    </div>
  );
}

export default Chatbox;
