import os
from dataclasses import dataclass
from anthropic import Anthropic
 
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
 
 
@dataclass
class ValidationResult:
    originalPrompt: str
    optimizedPrompt: str
    qualityScore: int
    passed: bool
    reasoning: str
    reactTrace: str = ""

# System prompt structured around the ReAcT framework (Read, Answer, Cite, Think 
# From NYIT's prompt-engineering frameworks guide:
# https://libguides.nyit.edu/promptengineering/promptframeworks)
VALIDATOR_SYSTEM_PROMPT = """You are a prompt-quality validator. You will be given an ORIGINAL prompt and an OPTIMIZED (shortened) version of it. Your job is to judge whether the optimized version still preserves the original's intent, meaning, and any explicit requirements (format, constraints, edge cases).
 
Work through the ReAcT framework, in order, labeling each step. Do not skip a step or merge them together:
 
READ: Restate, in your own words, every distinct requirement in the ORIGINAL prompt -- intent, tone, format, constraints, edge cases, and any examples. List them as short bullet points.
ANSWER: For each requirement listed in READ, state plainly whether the OPTIMIZED prompt still satisfies it (yes / no / weakened).
CITE: For every requirement you marked "no" or "weakened", quote the exact phrase from the ORIGINAL that establishes it, and note what (if anything) replaced it in the OPTIMIZED version. If everything was preserved, write "No losses to cite."
THINK: Reason about whether any drop or change identified above would actually change the model's output in practice, versus being a harmless phrasing difference.
 
Then, after THINK, end your reply with exactly these three lines and nothing after them:
SCORE: <integer 1-10>
PASSED: <yes or no>
REASON: <one short sentence explaining the score, grounded in what you found in CITE/THINK>
 
Scoring guide:
- 9-10: Optimized prompt is functionally identical in intent and requirements.
- 6-8: Minor phrasing differences, but intent and requirements are fully preserved.
- 3-5: Some meaningful loss — a constraint, example, or nuance was dropped or changed.
- 1-2: The optimized prompt would likely produce a meaningfully different or worse result.
 
PASSED should be "yes" only if the score is 6 or higher. Be strict — a shorter prompt that changes meaning is a failure, even if it saves tokens. Base the score only on what you actually found in READ/ANSWER/CITE/THINK, not on a general impression.
"""

"""
* @brief Builds the message sent to the validator LLM.
* @post
* 1. The original and optimized prompts are both included, clearly labeled.
* 2. A single combined string is returned, ready to send to the model.
"""
def buildUserMessage(originalPrompt: str, optimizedPrompt: str) -> str:
    return (
        f"original prompt:\n{originalPrompt}\n\n"
        f"optimized prompt:\n{optimizedPrompt}"
        )
    
"""
* @brief Parses the validator LLM's reply into its parts.
* @post
* 1. The SCORE, PASSED, and REASON lines are extracted from the reply.
* 2. If parsing fails for any field, safe fallback defaults are used
*    (score 1, passed False) rather than raising an error.
* 3. Everything before the final SCORE/PASSED/REASON block (the
*    READ/ANSWER/CITE/THINK trace) is kept as-is so the reasoning behind
*    the verdict stays inspectable, not just the verdict itself.
* 4. A tuple of (score, passed, reason, reactTrace) is returned.
"""
def parseValidatorReply(reply: str) -> tuple[float, bool, str, str]:
    score = 1
    passed = False
    reason = "Could not parse Agent 3, Validator, response."
    reply = reply.strip()
 
    for line in reply.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("SCORE:"):
            try:
                score = float(stripped.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif stripped.upper().startswith("PASSED:"):
            passed = stripped.split(":", 1)[1].strip().lower().startswith("y")
        elif stripped.upper().startswith("REASON:"):
            reason = stripped.split(":", 1)[1].strip()
 
    # Trace is everything before the SCORE line -- any reasoning
    # walkthrough that justifies the verdict above.
    scoreIndex = reply.upper().find("SCORE:")
    reactTrace = reply[:scoreIndex].strip() if scoreIndex != -1 else reply
 
    return score, passed, reason, reactTrace
 
"""
* @brief Sends both prompt versions to Claude for a quality comparison.
* @post
* 1. A request is sent to the Claude API with the validator system prompt.
* 2. The model's reply is parsed into score, passed, reason, and trace.
* 3. The raw parsed values are returned.
"""
def callValidatorLLM(originalPrompt: str, optimizedPrompt: str) -> tuple[float, bool, str, str]:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=VALIDATOR_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": buildUserMessage(originalPrompt, optimizedPrompt)
        }]
    )
    reply = response.content[0].text
    return parseValidatorReply(reply)
 
"""
* @brief Executes the full validation process comparing an original
* prompt against its optimized rewrite.
* @post
* 1. If the optimized prompt is identical to the original, validation
*    is skipped and an automatic pass is returned (no LLM call needed).
* 2. Otherwise, both versions are sent to the validator LLM.
* 3. A populated ValidationResult is returned, containing the score,
*    pass/fail verdict, reasoning, and reasoning trace.
"""
def validatePrompt(originalPrompt: str, optimizedPrompt: str) -> ValidationResult:
    if originalPrompt.strip() == optimizedPrompt.strip():
        return ValidationResult(
            originalPrompt=originalPrompt,
            optimizedPrompt=optimizedPrompt,
            qualityScore=10.0,
            passed=True,
            reasoning="No changes made — optimized prompt is identical to the original.",
            reactTrace="Skipped -- prompts are identical, no comparison needed.",
        )
 
    score, passed, reason, reactTrace = callValidatorLLM(originalPrompt, optimizedPrompt)
 
    return ValidationResult(
        originalPrompt=originalPrompt,
        optimizedPrompt=optimizedPrompt,
        qualityScore=score,
        passed=passed,
        reasoning=reason,
        reactTrace=reactTrace,
    )
 
if __name__ == "__main__":
    """
    original = "Please, could you kindly help me write a short story about a dragon? Thank you so much!"
    optimized = "Write a short story about a dragon."
    """
    original = "Write an article about social media"
    optimized = "Write a 500-word article about social media and teen mental health. Use a friendly tone and include three bulleted tips for parents."
    
    result = validatePrompt(original, optimized)
 
    print("Original:", result.originalPrompt)
    print()
    print("Optimized:", result.optimizedPrompt)
    print()
    print("Score:", result.qualityScore)
    print()
    print("Passed:", result.passed)
    print()
    print("Reasoning:", result.reasoning)
    print()