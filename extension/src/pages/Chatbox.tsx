import { useState, useEffect } from 'react';

function Chatbox() {
  const [promptValue, setPromptValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [sendMessage, setSendMessage] = useState("");
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

const GUEST_USER_ID = "00e5e341-5160-4908-9648-802a17def3ce";

async function getGuestUserId() {
  return GUEST_USER_ID;
}

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
      const userId = await getGuestUserId();
      const response = await fetch("http://127.0.0.1:8000/prompts/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          txt_prompt: txtPrompt,
        }),
      });
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail ?? `Backend request failed (${response.status}).`);
      }

      setSendMessage("Prompt saved to Supabase.");
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
            {isSending ? "Sending..." : "test"}
          </button>
        </div>
        {sendMessage && <p role="status">{sendMessage}</p>}
        {sendError && <p role="alert">{sendError}</p>}
      </div>
    </div>
  );
}

export default Chatbox;
