chrome.runtime.onMessage.addListener((request: any, _sender: any, sendResponse: (response?: any) => void) => {
  if (request.action === "get_chatgpt_text") {

    //detects for LLM promptbox( Only for chatGPT for now more soon)
    const promptBox = 
      document.querySelector('#prompt-textarea') || 
      document.querySelector('textarea');

    let text = "";
    if (promptBox) {
      // differnet LLM modles use different methods to extract the prompt from
      text = promptBox.textContent || (promptBox as HTMLElement).innerText || (promptBox as HTMLInputElement).value || "";
    } else {
      console.log("Could not find any prompt");
    }
    
    // Send the text back to the extension UI in the Chatbox.tsx
    sendResponse({ promptText: text });
  }
});