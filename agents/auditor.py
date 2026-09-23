import os
import re
from dataclasses import dataclass, field 
import tiktoken
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

@dataclass
class AuditResult:
    token_count: int
    estimatedCost: float
    issues: list[str] = field(default_factory = list)
    
"""
* @brief Counts the number of tokens in a text string
* @post
*  1. The text is encoded using the cl100k_base tokenizer
*  2. The number of resulting tokens is calculated then returned
"""
def countTokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

"""
* @brief Estimates the dollar cost of a prompt based on token count.
* @post
* 1. The token count is divided into per-1000-token units.
* 2. Cost is calculated using the provided (or default) rate.
* 3. The result is rounded to 3 decimal places and returned.
"""
def estimateCost(token_count: int, rate_per_100k: float = 0.003) -> float:
    return round((token_count / 1000) * rate_per_100k, 3)

"""
* @brief Runs fast, rule-based checks for common token-waste patterns.
* @post
* 1. The text's token-to-word ratio is checked for signs of verbiage meaning redundancy, or too wordy.
* 2. Filler/politeness word frequency is counted and flagged if excessive.
* 3. Excessive blank lines/whitespace are detected.
* 4. A list of human-readable issue descriptions is returned (empty if none found).
"""
def runRuleCheck(text: str, token_count: int) -> list[str]:
    issues = []
    word_count = len(text.split())
    
    if word_count > 0 or (token_count / word_count) > 1:
        issues.append("High token to word ratio. Possibly too verbose")
    
    filter_words = ["please", "thank you", "really", "basically", "essentially", "maybe", "possibly", "just", "hopefully", "somewhat", "amazing", "perfect", "literally", "best"]
    filler_hits = sum(text.lower().count(w) for w in filler_words)
    if filler_hits >= 3:
        issues.append(f"Too much filler words being used and or unnecessary politeness language ({filler_hits} instances happening)")
        
    if "\n\n\n" in text:
        issues.append("Unnecessary blank lines and or whitespace added")

    return issues
    
"""
* @brief Sends the prompt to the LLM for a deeper, subjective waste review.
* @post
* 1. A request is sent to the Claude API containing the prompt to review.
* 2. The model's reply is parsed for a list of flagged issues.
* 3. If the model responds "none found", an empty list is returned.
* 4. Otherwise, each non-empty line of the reply is returned as a separate issue string.
"""
def llmReview(text: str) -> list[str]:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "Review this prompt for token waste — redundant phrasing, "
                "unnecessary context, or verbosity. List specific issues, "
                "one per line. If none, say 'none found'.\n\n"
                f"PROMPT:\n{text}"
            )
        }]
    )
    
    reply = response.content[0].text
    if "none found" in reply.lower():
        return []
    return [line.strip("- ").strip() for line in reply.split("\n") if line.strip()]

"""
* @brief Determines overall severity rating for the audit result.
* @post
* 1. Token count and issue count are compared against the fixed thresholds.
* 2. A severity level of "High", "Medium", or "Low" is returned accordingly to count
"""
def determineSeverity(token_count: int, issue_count: int) -> str:
    if token_count > 800 or issue_count >= 3:
        return "High"
    elif token_count > 300 or issue_count >= 1:
        return "Medium"
    return "Low"

"""
* @brief Executes the full audit process on a single user-submitted prompt.
* @post
* 1. The prompt's token count and estimated cost are calculated.
* 2. Fast rule-based checks are run against the prompt.
* 3. If the prompt is long and no rule-based issues were found, an LLM review is triggered and its findings are appended.
* 4. A severity rating is computed from the final issue count and token count.
* 5. A populated AuditResult object is returned, containing all of the above.
"""
def auditPrompt(prompt: str) -> AuditResult:
    token_count = countTokens(prompt)
    cost = estimateCost(token_count)
    issues = runRuleCheck(prompt, token_count)

    if token_count > 500 and not issues:
        issues.extend(llm_review(prompt))

    severity = determineSeverity(token_count, len(issues))

    return AuditResult(
                        token_count=token_count,
                        estimated_cost=cost,
                        issues=issues,
                        severity=severity,
                        )


#Test dummy haha
if __name__ == "__main__":
    """
    test1 = "Hi world me llamo islam"
    test2 = "Please PLEASE please could you really kindly help me write a essay about some dragons?"
    test3 = ""

    print("Text:", test1)
    print("Token count:", countTokens(test1))
    print()

    print("Text:", test2)
    print("Token count:", countTokens(test2))
    print()

    print("Text:", test3)
    print("Token count:", countTokens(test3))
    """
    sample = "Please, please could you kindly just help me write a short story about a dragon please? I would appreciate it so much!"
    result = auditPrompt(sample)
    print(result)
