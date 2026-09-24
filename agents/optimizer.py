import os
import textwrap
from dataclasses import dataclass
import tiktoken
from anthropic import Anthropic
from agents.auditor import estimateCost
 
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
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=OPTIMIZER_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": buildUserMessage(prompt, issues)
        }]
    )
    return response.content[0].text.strip()

"""
* @brief Executes the full optimization process on a single prompt.
* @post
* 1. The original prompt's token count is calculated.
* 2. The prompt is sent to the optimizer LLM, along with any known
*    issues from Agent 1, and a rewritten version is returned.
* 3. The optimized prompt's token count is calculated.
* 4. Tokens saved and percent saved are computed (never negative).
* 5. A populated OptimizationResult is returned.
"""
def optimizePrompt(prompt: str, issues: list[str] = None) -> OptimizationResult:
    issues = issues or []
    originalTokens = countTokens(prompt)
 
    optimizedPrompt = callOptimizerLLM(prompt, issues)
    optimizedTokens = countTokens(optimizedPrompt)
 
    tokensSaved = max(originalTokens - optimizedTokens, 0)
    percentSaved = round((tokensSaved / originalTokens) * 100, 2) if originalTokens > 0 else 0.0
 
    return OptimizationResult(
        originalPrompt=prompt,
        optimizedPrompt=optimizedPrompt,
        originalTokens=originalTokens,
        optimizedTokens=optimizedTokens,
        tokensSaved=tokensSaved,
        percentSaved=percentSaved,
    )

"""
* @brief Formats an OptimizationResult as a side-by-side comparison table.
* @post
* 1. Each prompt is wrapped to fit within the prompt column.
* 2. Token counts and estimated cost per 1000 runs are shown for both prompts.
* 3. A summary row shows tokens and cost saved.
* 4. The table is returned as a single printable string.
"""
def formatComparisonTable(result: OptimizationResult, promptWidth: int = 50) -> str:
    headers = ["", "Prompt", "Tokens", "Cost / 1K Runs"]
    #Single-prompt costs round to $0.000, so show cost per 1000 runs instead
    originalCost = estimateCost(result.originalTokens * 1000)
    optimizedCost = estimateCost(result.optimizedTokens * 1000)
    rows = [
        ["Original", result.originalPrompt, str(result.originalTokens), f"${originalCost:.3f}"],
        ["Optimized", result.optimizedPrompt, str(result.optimizedTokens), f"${optimizedCost:.3f}"],
        ["Saved", f"{result.percentSaved}%", str(result.tokensSaved), f"${max(originalCost - optimizedCost, 0):.3f}"],
    ]

    #Split each row into lines so long prompts wrap inside their column
    wrappedRows = []
    for row in rows:
        promptLines = textwrap.wrap(row[1], promptWidth) or [""]
        wrappedRows.append([[row[0]], promptLines, [row[2]], [row[3]]])

    widths = [
        max(len(headers[col]), *(len(line) for row in wrappedRows for line in row[col]))
        for col in range(len(headers))
    ]
    divider = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def formatLine(cells: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(w) for cell, w in zip(cells, widths)) + " |"

    lines = [divider, formatLine(headers), divider]
    for row in wrappedRows:
        height = max(len(cell) for cell in row)
        for i in range(height):
            lines.append(formatLine([cell[i] if i < len(cell) else "" for cell in row]))
        lines.append(divider)
    return "\n".join(lines)
