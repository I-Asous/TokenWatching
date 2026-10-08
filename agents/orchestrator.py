import json
import os
from dataclasses import dataclass, field
 
from agents.auditor import auditPrompt, AuditResult
from agents.optimizer import optimizePrompt, OptimizationResult, RejectedAttempt
from agents.validator import validatePrompt, ValidationResult
from agents.tokens import DEFAULT_TARGET

MAX_OPTIMIZATION_ATTEMPTS = 3 #Is three too little? too much? idk come back to it

@dataclass
class OrchestrationResult:
    originalPrompt: str
    finalPrompt: str
    wasOptimized: bool
    auditResult: AuditResult
    attempts: list[ValidationResult] = field(default_factory=list)
    tokensSaved: int = 0
    percentSaved: float = 0.0
    changes: list[str] = field(default_factory=list)

"""
* @brief Runs the full Auditor -> Optimizer -> Validator pipeline on a
* single prompt then retrying the Optimizer with the rejected rewrite and the
* Validator's reason if a rewrite fails validation, and falling back to the original
* prompt if no rewrite passes within the retry budget.

* Token counts and savings are measured with the tokenizer of the target
* LLM the user is prompting ("chatgpt" or "claude").

* @post
* 1. The Auditor runs first; if it finds no issues, optimization is
*    skipped entirely and the original prompt is returned unchanged.
* 2. the Optimizer produces a rewrite using the Auditor's
*    issues (plus, on retries, every earlier rewrite the Validator
*    rejected along with its reason).
* 3. The Validator checks that rewrite against the original prompt.
* 4. If it passes, that rewrite becomes the final prompt and the loop
*    stops immediately NO wasted extra calls.
* 5. If it fails, the Optimizer is retried (up to
*    MAX_OPTIMIZATION_ATTEMPTS total attempts) with each rejected
*    rewrite and the Validator's reasoning fed back in, so each retry
*    sees exactly what it wrote and what that broke instead of
*    repeating the same mistake.
* 6. If a rewrite saves no tokens, the loop stops without validating it.
* 7. If no attempt passes, the original prompt is returned unchanged,
*    a rewrite the Validator rejected is never sent, even if it would
*    have saved tokens.
* 8. An OrchestrationResult capturing every attempt, the audit findings,
*    the final token/cost savings (if any), and the Optimizer's list of
*    changes for the accepted rewrite is returned.
"""
def runPipeline(prompt: str, target: str = DEFAULT_TARGET) -> OrchestrationResult:
    auditResult = auditPrompt(prompt, target)
 
    if not auditResult.issues:
        return OrchestrationResult(
            originalPrompt=prompt,
            finalPrompt=prompt,
            wasOptimized=False,
            auditResult=auditResult,
        )
 
    attempts: list[ValidationResult] = []
    rejectedAttempts: list[RejectedAttempt] = []
 
    for _ in range(MAX_OPTIMIZATION_ATTEMPTS):
        optimizationResult = optimizePrompt(prompt, auditResult.issues, target,
                                            rejectedAttempts=list(rejectedAttempts))

        #A rewrite that saves nothing (unchanged or longer) isn't worth a Validator call or a retry
        if optimizationResult.tokensSaved == 0:
            break

        validationResult = validatePrompt(prompt, optimizationResult.optimizedPrompt)
        attempts.append(validationResult)
 
        if validationResult.passed:
            return OrchestrationResult(
                originalPrompt=prompt,
                finalPrompt=optimizationResult.optimizedPrompt,
                wasOptimized=True,
                auditResult=auditResult,
                attempts=attempts,
                tokensSaved=optimizationResult.tokensSaved,
                percentSaved=optimizationResult.percentSaved,
                changes=optimizationResult.changes,
            )
        
        #Feed the rejected rewrite and the Validator's reasoning back in so the next
        #attempt sees what it wrote and what that broke, instead of failing the same way again
        rejectedAttempts.append(
            RejectedAttempt(optimizationResult.optimizedPrompt, validationResult.reasoning)
        )
 
    #No attempt passed validation within the retry amount SO fail gets closed.
    return OrchestrationResult(
        originalPrompt=prompt,
        finalPrompt=prompt,
        wasOptimized=False,
        auditResult=auditResult,
        attempts=attempts,
    )
    
if __name__ == "__main__":
    sample = ("Please, could you kindly help me write a short story? I would really appreciate it if you could make it about a dragon. Thank you so much!") 
    
    result = runPipeline(sample)

    print("Original:", result.originalPrompt)
    print()
    print("Final:", result.finalPrompt)
    print()
    print("Optimized:", result.wasOptimized)
    print()
    print("Audit severity:", result.auditResult.severity)
    print()
    print("Audit issues:", result.auditResult.issues)
    print()
    summary = {
        "attempts": [
            {
                "attempt": i,
                "score": attempt.qualityScore,
                "passed": attempt.passed,
                "reason": attempt.reasoning,
            }
            for i, attempt in enumerate(result.attempts, start=1)
        ],
    }
    if result.wasOptimized:
        summary["changes"] = result.changes
        summary["tokensSaved"] = result.tokensSaved
        summary["percentSaved"] = result.percentSaved
    print(json.dumps(summary, indent=2))
    print()
