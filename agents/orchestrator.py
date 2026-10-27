import json
import os
import logging
from dataclasses import dataclass, field
 
from anthropic import APIError

from agents.auditor import auditPrompt, AuditResult
from agents.optimizer import optimizePrompt, findRewriteProblems, OptimizationResult, RejectedAttempt
from agents.validator import validatePrompt, ValidationResult
from agents.locks import extractLocks
from agents.intent import detectIntent, describeIntent
from agents.vagueness import findVagueness, findOptionalMarkers, VaguenessReport
from agents.tokens import DEFAULT_TARGET

from agents.hooks.orchestrator import OrchestrationHooks

logger = logging.getLogger(__name__)

MAX_OPTIMIZATION_ATTEMPTS = 3 #Is three too little? too much? idk come back to it
#Lock kinds listed for the Optimizer up front. Code, URLs and steps are left out: the system prompt
#already says to copy them exactly, and repeating a long code block would cost more than it saves
PRESERVE_LOCK_KINDS = ("constraint", "number")

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
    #How vague the original is, with clarifying questions for the extension to ask. The Optimizer never
    #fills these gaps itself, since any guess changes the request
    vagueness: VaguenessReport = field(default_factory=VaguenessReport)
    #Set when an Optimizer or Validator API call failed and the original was returned because of it,
    #so a fallback from an outage can be told apart from "no rewrite passed"
    error: str | None = None

"""
* @brief Lists what a rewrite of this prompt must keep, for the Optimizer's message.
* @post
* 1. Each task the prompt asks for (intent.py) comes first, as "task: ..." lines.
* 2. Then every constraint and number lock (locks.py), as "rule: ..." and "number: ..." lines.
* 3. Then every optional request ("Maybe add tests."), as "optional: ..." lines, so the "maybe"
*    isn't cut as filler.
* 4. These are the same things the local checks reject a rewrite for, so the Optimizer sees
*    them before its first attempt instead of only after a rejection.
"""
def buildMustPreserve(prompt: str) -> list[str]:
    items = describeIntent(detectIntent(prompt))
    for lock in extractLocks(prompt):
        if lock.kind in PRESERVE_LOCK_KINDS:
            items.append(f"{'rule' if lock.kind == 'constraint' else lock.kind}: {lock.text}")
    items += [f"optional (keep it optional): {sentence}" for sentence in findOptionalMarkers(prompt)]
    return items

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
*    issues and the list of what this prompt must keep (buildMustPreserve),
*    plus, on retries, every earlier rewrite the Validator rejected along with its reason.
*    It drafts, checks and revises with tools on its own (see optimizer.py), and only
*    returns a rewrite that passes the local checks below.
* 3. The rewrite is checked locally again with findRewriteProblems (locks, tasks and
*    options), as a safety net. If anything is broken,
*    the attempt fails without a Validator call and those reasons are
*    passed back to the Optimizer. Otherwise the Validator checks the rewrite
*    against the original prompt.
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
*    have saved tokens. The same goes for a failed Optimizer or Validator API call
*    (including a timeout): the loop stops, the error is recorded on the result's
*    error field, and it is never fed back to the Optimizer (it says nothing about the rewrite).
* 8. The original's vagueness report (vagueness.py) is attached to every result, including when
*    optimization is skipped, so the extension can ask its clarifying questions.
* 9. An OrchestrationResult capturing every attempt, the audit findings,
*    the final token/cost savings (if any), and the Optimizer's list of
*    changes for the accepted rewrite is returned.
"""
def runPipeline(prompt: str, target: str = DEFAULT_TARGET, hook: OrchestrationHooks | None = None) -> OrchestrationResult:

    # we do this so if we want to run it without hooks, we can!
    hook = hook or OrchestrationHooks()

    hook.updateStage("auditing")
    auditResult = auditPrompt(prompt, target)
    hook.saveAudit(auditResult)

    vagueness = findVagueness(prompt)
 
    if not auditResult.issues:
        orchestrationResult = OrchestrationResult(
            originalPrompt=prompt,
            finalPrompt=prompt,
            wasOptimized=False,
            auditResult=auditResult,
            vagueness=vagueness,
        )
        hook.finishJob(orchestrationResult)
        return orchestrationResult
 
    attempts: list[ValidationResult] = []
    rejectedAttempts: list[RejectedAttempt] = []
    mustPreserve = buildMustPreserve(prompt)
    error = None
 
    for _ in range(MAX_OPTIMIZATION_ATTEMPTS):
        hook.updateStage("optimizing")
        try:
            optimizationResult = optimizePrompt(prompt, auditResult.issues, target,
                                                rejectedAttempts=list(rejectedAttempts),
                                                mustPreserve=mustPreserve)
        except APIError as apiError:
            error = f"Optimizer call failed: {apiError}"
            logger.warning("%s, returning the original prompt", error)
            break
        hook.saveOptimization(optimizationResult)

        #A rewrite that saves nothing (unchanged or longer) isn't worth a Validator call or a retry
        if optimizationResult.tokensSaved == 0:
            break

        hook.updateStage("validating")
        #Free local check first: a rewrite that drops a code block, URL, rule, step, number, task or option
        #is REJECTED without paying for a Validator call then exact reasons go back to the Optimizer.
        #The Optimizer already runs this check before it submits, so this is a safety net
        brokenLocks = findRewriteProblems(prompt, optimizationResult.optimizedPrompt)
        if brokenLocks:
            reason = "Dropped or changed required parts: " + "; ".join(brokenLocks)

            brokenLockValidation = ValidationResult(
                originalPrompt=prompt,
                optimizedPrompt=optimizationResult.optimizedPrompt,
                qualityScore=0,
                passed=False,
                reasoning=reason,
                reactTrace="Failed the local lock check, Validator not called.",
            )
            attempts.append(brokenLockValidation)
            rejectedAttempts.append(RejectedAttempt(optimizationResult.optimizedPrompt, reason))
            
            hook.saveValidation(brokenLockValidation)
            continue

        #An unvalidated rewrite is never sent, so a failed Validator call falls back to the original
        try:
            validationResult = validatePrompt(prompt, optimizationResult.optimizedPrompt)
        except APIError as apiError:
            error = f"Validator call failed: {apiError}"
            logger.warning("%s, returning the original prompt", error)
            break
        hook.saveValidation(validationResult)

        attempts.append(validationResult)
 
        if validationResult.passed:
            orchestrationResult = OrchestrationResult(
                originalPrompt=prompt,
                finalPrompt=optimizationResult.optimizedPrompt,
                wasOptimized=True,
                auditResult=auditResult,
                attempts=attempts,
                tokensSaved=optimizationResult.tokensSaved,
                percentSaved=optimizationResult.percentSaved,
                changes=optimizationResult.changes,
                vagueness=vagueness,
            )
            hook.finishJob(orchestrationResult)

            return orchestrationResult
        
        #Feed the rejected rewrite and the Validator's reasoning back in so the next
        #attempt sees what it wrote and what that broke, instead of failing the same way again
        rejectedAttempts.append(
            RejectedAttempt(optimizationResult.optimizedPrompt, validationResult.reasoning)
        )
    #No attempt passed validation within the retry amount (or an API call failed) SO fail gets closed.
    orchestrationResult = OrchestrationResult(
        originalPrompt=prompt,
        finalPrompt=prompt,
        wasOptimized=False,
        auditResult=auditResult,
        attempts=attempts,
        vagueness=vagueness,
        error=error,
    )
    hook.finishJob(orchestrationResult)
    return orchestrationResult
    
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
