import os
from dataclasses import dataclass, field
 
from agents.auditor import auditPrompt, AuditResult
from agents.optimizer import optimizePrompt, OptimizationResult
from agents.validator import validatePrompt, ValidationResult

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

"""
* @brief Runs the full Auditor -> Optimizer -> Validator pipeline on a
* single prompt then retrying the Optimizer with the Validator's own rejection
* reason if a rewrite fails validation, and falling back to the original
* prompt if no rewrite passes within the retry budget.

* @post
* 1. The Auditor runs first; if it finds no issues, optimization is
*    skipped entirely and the original prompt is returned unchanged.
* 2. the Optimizer produces a rewrite using the Auditor's
*    issues (plus, on retries, the Validator's prior rejection reason
*    appended as an extra issue to fix).
* 3. The Validator checks that rewrite against the original prompt.
* 4. If it passes, that rewrite becomes the final prompt and the loop
*    stops immediately NO wasted extra calls.
* 5. If it fails, the Optimizer is retried (up to
*    MAX_OPTIMIZATION_ATTEMPTS total attempts) with the Validator's
*    reasoning fed back in, so each retry knows specifically what the
*    last attempt broke instead of repeating the same mistake.
* 6. If a rewrite saves no tokens, the loop stops without validating it.
* 7. If no attempt passes, the original prompt is returned unchanged,
*    a rewrite the Validator rejected is never sent, even if it would
*    have saved tokens.
* 8. An OrchestrationResult capturing every attempt, the audit findings,
*    and the final token/cost savings (if any) is returned.
"""
def runPipeline(prompt: str) -> OrchestrationResult:
    auditResult = auditPrompt(prompt)
 
    if not auditResult.issues:
        return OrchestrationResult(
            originalPrompt=prompt,
            finalPrompt=prompt,
            wasOptimized=False,
            auditResult=auditResult,
        )
 
    issues = list(auditResult.issues)
    attempts: list[ValidationResult] = []
 
    for attemptNumber in range(1, MAX_OPTIMIZATION_ATTEMPTS + 1):
        optimizationResult = optimizePrompt(prompt, issues)

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
            )
        
        """
        Feed the Validator's own reasoning back in so the next attempt
        knows specifically what it broke, instead of repeating the same
        rewrite and failing the same way again
        """
        issues.append(
            f"Optimizer attempt {attemptNumber} was rejected by the Validator: {validationResult.reasoning}"
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
    print(f"Attempts: {len(result.attempts)}")
    for i, attempt in enumerate(result.attempts, start=1):
        print(f"  Attempt {i}: score={attempt.qualityScore}, passed={attempt.passed}, reason={attempt.reasoning}")
    if result.wasOptimized:
        print(f"Tokens saved: {result.tokensSaved} ({result.percentSaved}%)") 