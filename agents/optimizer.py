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