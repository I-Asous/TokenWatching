import json
import os
import logging
from dataclasses import dataclass, field, replace
 
from anthropic import APIError

from agents.auditor import auditPrompt, runRuleCheck, AuditResult
from agents.optimizer import (optimizePrompt, findRewriteProblems, rewriteResult, OptimizationResult,
                              RejectedAttempt, Answer, Rewrite)
from agents.validator import validatePrompt, ValidationResult
from agents.locks import extractLocks
from agents.local_rewrite import localRewrite, isFillerOnlyEdit
from agents.intent import detectIntent, describeIntent
from agents.vagueness import findVagueness, findOptionalMarkers, VaguenessReport
from agents.prompt_types import detectPromptTypes, combineProfiles, DEFAULT_TYPE
from agents.tokens import countTokens, DEFAULT_TARGET

from agents.hooks.orchestrator import OrchestrationHooks

logger = logging.getLogger(__name__)

#The Optimizer fixes local-check failures, too small a saving and Validator rejections inside its own tool
#loop (SubmissionValidator, up to optimizer.MAX_VALIDATIONS), so a real run makes one attempt. A retry here
#only happens when the Optimizer returns a rewrite it didn't validate; each costs up to MAX_TOOL_TURNS
#Optimizer calls plus a Validator call while the user waits
MAX_OPTIMIZATION_ATTEMPTS = 2
#Lock kinds listed for the Optimizer up front. Code, URLs and steps are left out: the system prompt
#already says to copy them exactly, and repeating a long code block would cost more than it saves
PRESERVE_LOCK_KINDS = ("constraint", "number")
#A prompt shorter than this rarely has MIN_TOKENS_SAVED to cut, so it isn't worth an Optimizer call. Tune on real runs
MIN_TOKENS_FOR_OPTIMIZER = 15
#A rewrite must save at least this many tokens and this share of the prompt to be worth a Validator call or a retry.
#The share stays low because a long code block with a polite wrapper can save many tokens but few percent. Tune on real runs
MIN_TOKENS_SAVED = 5
MIN_PERCENT_SAVED = 2.0
#Most clarifying questions answered across every round for one prompt. ask_user is offered only below it,
#so the Optimizer can ask again when answers leave a gap but can't keep the person in a loop. Tune on real runs
MAX_ANSWERED_QUESTIONS = 4

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
    #Every type the prompt was detected as, strictest first (prompt_types.py). Their combined profile
    #decided which audit checks ran, the Optimizer's type rules and the Validator's pass score
    promptTypes: list[str] = field(default_factory=lambda: [DEFAULT_TYPE])
    #Set when an Optimizer or Validator API call failed and no LLM rewrite was used because of it
    #(the original or the local rewrite was returned), so a fallback from an outage can be told apart
    #from "no rewrite passed"
    error: str | None = None
    #Set when the Optimizer chose to ask instead of rewriting (ask_user): the questions to show the person.
    #Their answers come back in the next runPipeline call, with the same prompt
    needsClarification: bool = False
    questions: list[str] = field(default_factory=list)

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
* @brief The pass recorded for a rewrite that only deleted politeness and filler (isFillerOnlyEdit).
* @post
* 1. Nothing the prompt asks for was removed or reworded, so no Validator call is made.
* 2. It's saved like any other validation, so the run's history shows why the Validator wasn't called.
"""
def fillerOnlyValidation(prompt: str, rewrite: str) -> ValidationResult:
    return ValidationResult(
        originalPrompt=prompt,
        optimizedPrompt=rewrite,
        qualityScore=10,
        passed=True,
        reasoning="Only politeness and filler were deleted, nothing was reworded.",
        reactTrace="Deletion-only edit checked locally, Validator not called.",
    )

"""
* @brief Adds the person's answers to clarifying questions to their prompt.
* @post
* 1. Without answers the prompt is returned as is.
* 2. Each answer goes on its own line after its question ("Who is it for? Beginners"), so the
*    prompt still reads well if it's sent like this, when no rewrite passes.
* 3. This is the text the Auditor, the Optimizer and the Validator work on.
"""
def clarifyPrompt(prompt: str, answers: list[Answer]) -> str:
    if not answers:
        return prompt
    lines = "\n".join(f"{answer.question.strip()} {answer.answer.strip()}" for answer in answers)
    return f"{prompt.rstrip()}\n\n{lines}"

"""
* @brief The text the local checks compare a rewrite of a clarified prompt against.
* @post
* 1. Without answers it's the prompt itself.
* 2. Otherwise it's the prompt with each answer on its own line, without the questions: the local
*    checks would read "Who is it for?" as a question the rewrite has to keep asking.
* 3. Numbers, rules and tasks in the answers are kept, so a rewrite may state them and must not drop them.
"""
def referencePrompt(prompt: str, answers: list[Answer]) -> str:
    if not answers:
        return prompt
    return prompt.rstrip() + "\n\n" + "\n".join(answer.answer.strip() for answer in answers)

"""
* @brief Adds the person's answers to a local rewrite of their own prompt.
* @post
* 1. The local rewrite is made from the prompt alone, since closing thanks are only deleted at the end
*    of a prompt, and the answers would come after them.
* 2. The answers are added after it as in clarifyPrompt, and its savings are counted against the
*    clarified prompt, the text it replaces.
"""
def withAnswers(localResult: OptimizationResult, clarified: str, answers: list[Answer],
                target: str) -> OptimizationResult:
    optimizedPrompt = clarifyPrompt(localResult.optimizedPrompt, answers)
    originalTokens = countTokens(clarified, target)
    optimizedTokens = countTokens(optimizedPrompt, target)
    tokensSaved = max(originalTokens - optimizedTokens, 0)
    return replace(localResult, originalPrompt=clarified, optimizedPrompt=optimizedPrompt,
                   originalTokens=originalTokens, optimizedTokens=optimizedTokens, tokensSaved=tokensSaved,
                   percentSaved=round(tokensSaved / originalTokens * 100, 2) if originalTokens else 0.0)

#A rewrite saves enough to be worth a Validator call, a retry or offering it to the Optimizer
def savesEnough(optimizationResult: OptimizationResult) -> bool:
    return optimizationResult.tokensSaved >= MIN_TOKENS_SAVED and optimizationResult.percentSaved >= MIN_PERCENT_SAVED

"""
* @brief Validates the Optimizer's submissions during its tool loop (passed to optimizePrompt as validate).
* @post
* 1. Each draft is saved through the hooks as an optimization, then its validation, in that order, so the
*    backend links every verdict to the rewrite it judged, the same as a validated attempt outside the loop.
* 2. A filler-only edit passes without a Validator call (fillerOnlyValidation). Anything else goes to the
*    Validator with the prompt type's pass score and rules.
* 3. Every validation is added to attempts; a failed one also to rejectedAttempts, a passed one to accepted
*    (by rewrite text), so the orchestrator uses that verdict instead of validating the rewrite again.
* 4. A failed Validator call sets apiFailed and is raised, so the run's error says the Validator failed.
"""
class SubmissionValidator:
    def __init__(self, clarified: str, target: str, passScore: int, typeRules: str, hook: OrchestrationHooks,
                 attempts: list[ValidationResult], rejectedAttempts: list[RejectedAttempt]):
        self.clarified = clarified
        self.target = target
        self.passScore = passScore
        self.typeRules = typeRules
        self.hook = hook
        self.attempts = attempts
        self.rejectedAttempts = rejectedAttempts
        self.accepted: dict[str, ValidationResult] = {}
        self.apiFailed = False

    def __call__(self, rewrite: Rewrite) -> ValidationResult:
        draft = rewriteResult(self.clarified, rewrite, self.target)
        self.hook.saveOptimization(draft)
        self.hook.updateStage("validating")
        if isFillerOnlyEdit(self.clarified, draft.optimizedPrompt):
            validation = fillerOnlyValidation(self.clarified, draft.optimizedPrompt)
        else:
            try:
                validation = validatePrompt(self.clarified, draft.optimizedPrompt,
                                            passScore=self.passScore, typeRules=self.typeRules)
            except APIError:
                self.apiFailed = True
                raise
        self.hook.saveValidation(validation)
        self.attempts.append(validation)
        if validation.passed:
            self.accepted[draft.optimizedPrompt] = validation
        else:
            self.rejectedAttempts.append(RejectedAttempt(draft.optimizedPrompt, validation.reasoning))
        self.hook.updateStage("optimizing")
        return validation

#The result when no rewrite is used: the prompt as the person wrote it, with their answers if they gave any
def unchangedResult(prompt: str, finalPrompt: str, auditResult: AuditResult, vagueness: VaguenessReport,
                    promptTypes: list[str], attempts: list[ValidationResult] = None,
                    error: str | None = None) -> OrchestrationResult:
    return OrchestrationResult(
        originalPrompt=prompt,
        finalPrompt=finalPrompt,
        wasOptimized=False,
        auditResult=auditResult,
        attempts=attempts or [],
        vagueness=vagueness,
        promptTypes=promptTypes,
        error=error,
    )

#The result for a rewrite that passed, from the Optimizer or the local rewrite
def acceptedResult(prompt: str, optimizationResult: OptimizationResult, auditResult: AuditResult,
                   attempts: list[ValidationResult], vagueness: VaguenessReport,
                   promptTypes: list[str], error: str | None = None) -> OrchestrationResult:
    return OrchestrationResult(
        originalPrompt=prompt,
        finalPrompt=optimizationResult.optimizedPrompt,
        wasOptimized=True,
        auditResult=auditResult,
        attempts=attempts,
        tokensSaved=optimizationResult.tokensSaved,
        percentSaved=optimizationResult.percentSaved,
        changes=optimizationResult.changes,
        vagueness=vagueness,
        promptTypes=promptTypes,
        error=error,
    )

#Records a local rewrite's pass (no Validator call) and returns it as the accepted result
def acceptLocal(prompt: str, clarified: str, localResult: OptimizationResult, auditResult: AuditResult,
                attempts: list[ValidationResult], vagueness: VaguenessReport, promptTypes: list[str],
                hook: OrchestrationHooks, error: str | None = None) -> OrchestrationResult:
    localValidation = fillerOnlyValidation(clarified, localResult.optimizedPrompt)
    hook.saveValidation(localValidation)
    return acceptedResult(prompt, localResult, auditResult, attempts + [localValidation], vagueness, promptTypes, error)

"""
* @brief Runs the full Auditor -> Optimizer -> Validator pipeline on a
* single prompt then retrying the Optimizer with the rejected rewrite and the
* Validator's reason if a rewrite fails validation, and falling back to the original
* prompt if no rewrite passes within the retry budget.

* Token counts and savings are measured with the tokenizer of the target
* LLM the user is prompting ("chatgpt" or "claude").

* @post
* 0. The prompt's types are detected first (prompt_types.py) and their profiles combined, strictest
*    setting winning. The profile is passed on: skipChecks to the Auditor, optimizerRules to the
*    Optimizer and the Validator (so both work from the same rules), passScore to the Validator.
*    A type with optimize=False skips optimization.
* 0b. If the person answered clarifying questions (answers, from an earlier ask_user or the vagueness
*    report), the answers are added to the prompt (clarifyPrompt) and the whole pipeline runs on that.
*    The local checks compare rewrites against the prompt plus the answers alone (referencePrompt).
* 1. The Auditor runs first; if it finds no issues, optimization is
*    skipped entirely and the original prompt is returned unchanged. With answers, the Optimizer
*    always runs, since working them into the prompt is what the person asked for.
* 1b. If deleting the prompt's politeness and filler fixes everything the rule checks found
*    (local_rewrite.py) and saves at least MIN_TOKENS_SAVED and MIN_PERCENT_SAVED, that rewrite
*    is returned with no Optimizer or Validator call (not with answers, which need the Optimizer).
* 1c. A prompt under MIN_TOKENS_FOR_OPTIMIZER tokens is returned unchanged with no Optimizer call
*    (unless it has answers).
* 2. the Optimizer produces a rewrite using the Auditor's
*    issues, the type's rules and the list of what this prompt must keep (buildMustPreserve),
*    plus, on retries, every earlier rewrite the Validator rejected along with its reason.
*    It submits through a tool and revises after any refusal (see optimizer.py), and only
*    returns a rewrite that passes the local checks below.
* 2b. The Optimizer may instead choose one of two other tools:
*    - use_local_rewrite, offered when deleting politeness and filler saves enough but leaves other
*      issues. That rewrite is accepted with no Validator call.
*    - ask_user, offered when the vagueness report has questions and fewer than MAX_ANSWERED_QUESTIONS
*      have been answered. No rewrite is made: the result has needsClarification set and the
*      Optimizer's questions, for the extension to ask.
* 3. The rewrite is checked locally again with findRewriteProblems (locks, tasks and
*    options), as a safety net. If anything is broken,
*    the attempt fails without a Validator call and those reasons are
*    passed back to the Optimizer. Otherwise the Validator checks the rewrite
*    against the original prompt, with the type's rules and pass score, unless the rewrite
*    only deleted politeness and filler (isFillerOnlyEdit), which passes without a Validator call.
* 4. If it passes, that rewrite becomes the final prompt and the loop
*    stops immediately NO wasted extra calls.
* 5. If it fails, the Optimizer is retried (up to
*    MAX_OPTIMIZATION_ATTEMPTS total attempts) with each rejected
*    rewrite and the Validator's reasoning fed back in, so each retry
*    sees exactly what it wrote and what that broke instead of
*    repeating the same mistake.
* 6. If a rewrite saves under MIN_TOKENS_SAVED tokens or MIN_PERCENT_SAVED of the prompt, the
*    loop stops without validating or retrying it. With answers, any rewrite that changed the
*    prompt and isn't longer goes on, since it works the answers in.
* 7. If no attempt passes, the local rewrite offered in 2b is returned if there is one, otherwise the
*    original prompt (with the answers, if any) unchanged. A rewrite the Validator rejected is never sent,
*    even if it would have saved tokens. The same goes for a failed Optimizer or Validator API call
*    (including a timeout): the loop stops, the error is recorded on the result's
*    error field, and it is never fed back to the Optimizer (it says nothing about the rewrite).
* 8. The original's vagueness report (vagueness.py) is attached to every result, including when
*    optimization is skipped, so the extension can ask its clarifying questions.
* 9. An OrchestrationResult capturing every attempt, the audit findings,
*    the final token/cost savings (if any), and the Optimizer's list of
*    changes for the accepted rewrite is returned.
"""
def runPipeline(prompt: str, target: str = DEFAULT_TARGET, hook: OrchestrationHooks | None = None,
                answers: list[Answer] | None = None) -> OrchestrationResult:

    # we do this so if we want to run it without hooks, we can!
    hook = hook or OrchestrationHooks()

    answers = [answer for answer in answers or [] if answer.answer.strip()]
    clarified = clarifyPrompt(prompt, answers)
    reference = referencePrompt(prompt, answers)

    promptTypes = detectPromptTypes(clarified)
    profile = combineProfiles(promptTypes)

    hook.updateStage("auditing")
    auditResult = auditPrompt(clarified, target, skipChecks=profile.skipChecks)
    hook.saveAudit(auditResult)

    #Read from the answers too, so a gap they filled isn't suggested as a question again
    vagueness = findVagueness(reference)

    if not profile.optimize or (not auditResult.issues and not answers):
        orchestrationResult = unchangedResult(prompt, clarified, auditResult, vagueness, promptTypes)
        hook.finishJob(orchestrationResult)
        return orchestrationResult

    #Deleting politeness and filler is free and can't change the request. When it fixes everything the
    #rule checks found, it's the whole rewrite: neither the Optimizer nor the Validator is called.
    #One that leaves other issues is offered to the Optimizer, and is the fallback if no LLM rewrite passes.
    #One that saves too little goes to the Optimizer instead, same bar as an Optimizer rewrite
    localResult = localRewrite(prompt, target, profile.skipChecks, requireClean=False)
    if localResult and answers:
        localResult = withAnswers(localResult, clarified, answers, target)
    if localResult and not savesEnough(localResult):
        localResult = None
    if localResult and not answers and not runRuleCheck(localResult.optimizedPrompt, localResult.optimizedTokens,
                                                         profile.skipChecks):
        hook.updateStage("optimizing")
        hook.saveOptimization(localResult)
        orchestrationResult = acceptLocal(prompt, clarified, localResult, auditResult, [], vagueness, promptTypes, hook)
        hook.finishJob(orchestrationResult)
        return orchestrationResult

    if auditResult.token_count < MIN_TOKENS_FOR_OPTIMIZER and not answers:
        orchestrationResult = unchangedResult(prompt, clarified, auditResult, vagueness, promptTypes)
        hook.finishJob(orchestrationResult)
        return orchestrationResult

    attempts: list[ValidationResult] = []
    rejectedAttempts: list[RejectedAttempt] = []
    mustPreserve = buildMustPreserve(reference)
    maxQuestions = max(MAX_ANSWERED_QUESTIONS - len(answers), 0)
    error = None
    submissionValidator = SubmissionValidator(clarified, target, profile.passScore, profile.optimizerRules, hook,
                                              attempts, rejectedAttempts)

    for _ in range(MAX_OPTIMIZATION_ATTEMPTS):
        hook.updateStage("optimizing")
        try:
            optimizationResult = optimizePrompt(clarified, auditResult.issues, target,
                                                rejectedAttempts=list(rejectedAttempts),
                                                mustPreserve=mustPreserve,
                                                typeRules=profile.optimizerRules,
                                                localResult=localResult,
                                                questions=vagueness.questions,
                                                maxQuestions=maxQuestions,
                                                answers=answers,
                                                checkAgainst=reference if answers else None,
                                                #Same bar as savesEnough below; with answers only a longer rewrite is refused
                                                minTokensSaved=0 if answers else MIN_TOKENS_SAVED,
                                                minPercentSaved=0.0 if answers else MIN_PERCENT_SAVED,
                                                validate=submissionValidator)
        except APIError as apiError:
            agent = "Validator" if submissionValidator.apiFailed else "Optimizer"
            error = f"{agent} call failed: {apiError}"
            logger.warning("%s, returning the original prompt", error)
            break

        #Validated during the Optimizer's loop: the draft and its verdict are already saved and in attempts
        if (optimizationResult.action == "rewrite"
                and optimizationResult.optimizedPrompt in submissionValidator.accepted):
            orchestrationResult = acceptedResult(prompt, optimizationResult, auditResult, attempts, vagueness,
                                                 promptTypes)
            hook.finishJob(orchestrationResult)
            return orchestrationResult
        hook.saveOptimization(optimizationResult)

        #The Optimizer chose to ask: nothing is rewritten until the person answers
        if optimizationResult.action == "ask_user":
            orchestrationResult = unchangedResult(prompt, clarified, auditResult, vagueness, promptTypes, attempts)
            orchestrationResult.needsClarification = True
            orchestrationResult.questions = optimizationResult.questions
            hook.finishJob(orchestrationResult)
            return orchestrationResult

        #The Optimizer chose the local rewrite, which only deleted politeness and filler: no Validator call
        if optimizationResult.action == "local":
            orchestrationResult = acceptLocal(prompt, clarified, optimizationResult, auditResult, attempts,
                                              vagueness, promptTypes, hook)
            hook.finishJob(orchestrationResult)
            return orchestrationResult

        #A rewrite that saves little or nothing (unchanged or longer) isn't worth a Validator call or a retry.
        #With answers, saving isn't the point: any rewrite that works them in without growing goes on
        if answers:
            if (optimizationResult.optimizedPrompt == clarified
                    or optimizationResult.optimizedTokens > optimizationResult.originalTokens):
                break
        elif not savesEnough(optimizationResult):
            break

        hook.updateStage("validating")
        #Free local check first: a rewrite that drops a code block, URL, rule, step, number, task or option
        #is REJECTED without paying for a Validator call then exact reasons go back to the Optimizer.
        #The Optimizer already runs this check before it submits, so this is a safety net
        brokenLocks = findRewriteProblems(reference, optimizationResult.optimizedPrompt)
        if brokenLocks:
            reason = "Dropped or changed required parts: " + "; ".join(brokenLocks)

            brokenLockValidation = ValidationResult(
                originalPrompt=clarified,
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

        #A rewrite that only deleted politeness and filler can't have changed the request, so it skips the
        #Validator. Anything else is validated: an unvalidated rewrite is never sent, so a failed call falls back
        if isFillerOnlyEdit(clarified, optimizationResult.optimizedPrompt):
            validationResult = fillerOnlyValidation(clarified, optimizationResult.optimizedPrompt)
        else:
            try:
                validationResult = validatePrompt(clarified, optimizationResult.optimizedPrompt,
                                                  passScore=profile.passScore,
                                                  typeRules=profile.optimizerRules)
            except APIError as apiError:
                error = f"Validator call failed: {apiError}"
                logger.warning("%s, returning the original prompt", error)
                break
        hook.saveValidation(validationResult)

        attempts.append(validationResult)

        if validationResult.passed:
            orchestrationResult = acceptedResult(prompt, optimizationResult, auditResult, attempts, vagueness, promptTypes)
            hook.finishJob(orchestrationResult)

            return orchestrationResult

        #Feed the rejected rewrite and the Validator's reasoning back in so the next
        #attempt sees what it wrote and what that broke, instead of failing the same way again
        rejectedAttempts.append(
            RejectedAttempt(optimizationResult.optimizedPrompt, validationResult.reasoning)
        )
    #No LLM rewrite passed within the retry amount (or an API call failed) SO fail gets closed:
    #the local rewrite still saves tokens without changing the request, otherwise the prompt goes back as is
    if localResult:
        hook.saveOptimization(localResult)
        orchestrationResult = acceptLocal(prompt, clarified, localResult, auditResult, attempts, vagueness,
                                          promptTypes, hook, error)
    else:
        orchestrationResult = unchangedResult(prompt, clarified, auditResult, vagueness, promptTypes, attempts, error)
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
    print("Prompt types:", result.promptTypes)
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
