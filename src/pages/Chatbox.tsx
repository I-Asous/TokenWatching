import { useState, useEffect } from 'react';

function Chatbox() {
  const [promptValue, setPromptValue] = useState("");

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
            // 3. Put the response into state
            if (response && response.promptText) {
              setPromptValue(response.promptText);
            }
          }
        );
      }
    });
  }, []);

  return (
    <div>
      <div className="Board1">
        <h4>Enter Prompt</h4>

        {/* Bind state to the textarea so the text appears automatically */}
        <textarea 
          className="promptext"
          value={promptValue}
          onChange={(e) => setPromptValue(e.target.value)}
        />
      </div>
    </div>
  );
}

export default Chatbox;