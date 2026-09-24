import os
from dataclasses import dataclass
import tiktoken
from anthropic import Anthropic
 
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
 
 
@dataclass
class OptimizationResult:
    originalPrompt: str
    optimizedPrompt: str
    originalTokens: int
    optimizedTokens: int
    tokensSaved: int
    percentSaved: float
    
OPTIMIZER_SYSTEM_PROMPT = """You are a prompt optimizer. Rewrite the given prompt to reduce its token count while preserving its exact intent and meaning.
 
Apply these principles:
- Remove filler/politeness phrasing ("please", "kindly", "thank you") — models don't need social cues.
- Replace verbose phrasing with direct, imperative instructions.
- Remove redundant context or repeated instructions.
- Keep any examples intact — they usually improve output quality and shouldn't be cut for length.
- Never remove specificity that affects output quality (format requirements, constraints, edge cases).
- If the prompt is already concise, return it unchanged rather than forcing a rewrite.
 
Example:
BEFORE: "Please, could you kindly help me write a short story? I would really appreciate it if you could make it about a dragon. Thank you so much!"
AFTER: "Write a short story about a dragon."
 
Return ONLY the rewritten prompt text. No explanation, no preamble.
"""

"""
* @brief Counts the number of tokens in a text string.
* @post
* 1. The text is encoded using the cl100k_base tokenizer.
* 2. The number of resulting tokens is calculated then returned.
"""
def countTokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

"""
* @brief Builds the message sent to the optimizer LLM, including any
* known issues from Agent 1 so the rewrite targets real problems.
* @post
* 1. The original prompt is wrapped in delimiters.
* 2. If issues were provided, they're listed to focus the rewrite.
* 3. A single combined string is returned.
"""
def buildUserMessage(prompt: str, issues: list[str]) -> str:
    issuesSection = ""
    if issues:
        issuesList = "\n".join(f"- {issue}" for issue in issues)
        issuesSection = f"Known issues found in prompt:\n{issuesList}\n\n"
 
    return (
            f"{issuesSection}"
            f"PROMPT TO OPTIMIZE:\n{prompt}"
            )

"""
* @brief Sends the prompt to Claude for optimization.
* @post
* 1. A request is sent to the Claude API with the optimizer system prompt.
* 2. The model's rewritten prompt is extracted from the response.
* 3. The raw rewritten text is returned, stripped of whitespace.
"""
def callOptimizerLLM(prompt: str, issues: list[str]) -> str:
    return 0