## helpar to structure the response into a proper insert and stuff (bc sometimes it has more stuff...)
from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult
from agents.orchestrator import OrchestrationResult
from agents.validator import ValidationResult
from schema.audit import AuditInsert
from schema.optimized_prompts import OptimizedPromptInsert
from schema.orchestration import OrchestrationUpdate
from schema.validation import ValidationInsert


def structure_response(result, user_id: str, run_id=None, optimized_prompt_id=None, feedback_validation_id=None, final_optimized_prompt_id=None):
    if isinstance(result, AuditResult):
        return AuditInsert(user_id=user_id, run_id=run_id, token_count=result.token_count, estimated_cost=result.estimatedCost, severity=result.severity)
    
    if isinstance(result, OptimizationResult):
        return OptimizedPromptInsert(
            user_id=user_id,
            run_id=run_id,
            feedback_validation_id=feedback_validation_id,
            txt_prompt=result.optimizedPrompt,
            tokens=result.optimizedTokens,
            tokens_saved=result.tokensSaved,
            percent_saved=result.percentSaved,
            unchanged=result.optimizedPrompt == result.originalPrompt,
            changes=result.changes,
            preserved_constraints=result.preservedConstraints)
    
    if isinstance(result, ValidationResult):
        return ValidationInsert(user_id=user_id, optimized_prompt_id=optimized_prompt_id,
                                score=result.qualityScore, passed=result.passed,
                                reasoning=result.reasoning, react_trace=result.reactTrace)
    
    if isinstance(result, OrchestrationResult):
        return OrchestrationUpdate(status="done", final_optimized_prompt_id=final_optimized_prompt_id,)

    
    raise TypeError(f"{type(result).__name__} is not a value type to structure...")