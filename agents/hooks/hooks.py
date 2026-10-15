# this might have to be 3 separate files but teehee

from agents.auditor import AuditResult

from agents.optimizer import OptimizationResult
from agents.validator import ValidationResult
from backend.repository.optimized_prompts import create_optimized_prompt
from backend.repository.prompts import create_prompt
from backend.repository.audit import create_audit
from backend.repository.validation import create_validation

# allow the orhchestrator to save the audit result
def saveAuditResult(result: AuditResult):
    # try:
    #     create

    pass

# allow the orchestrator to save the optimized prompt
def saveOptimizedPrompt(result: OptimizationResult):
    try:
        create_optimized_prompt(result)

    ##TODO: this crashes the code. we need to make this so that there can be 2 things:
    # 1. either we retry until it works
    # 2. or we just log it and move on
    #
    # FOR OPTION 1, we might have to make a queue system that will retry until it works. but for now, let's just log it and move on
    except Exception as e:
        raise RuntimeError(f"Failed to save optimized prompt: {str(e)}")

# i feel like this can be just saved with validation result...
# def saveRejection(result: RejectedAttempt):
#     pass

# allow the orchestrator to save the validation
def saveValidationResult(result: ValidationResult):
    pass
