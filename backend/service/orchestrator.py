# TODO: so many imports can we like not...

from datetime import datetime

# from agents.orchestrator import runPipeline 
# from schema.orchestrator import OrchestrationResult
from dataclasses import dataclass
import logging

from agents.orchestrator import OrchestrationResult
from agents.validator import ValidationResult
from repository.audit import create_audit
from repository.orchestration import create_orchestration, update_orchestration, update_orchestration_status
from repository.prompts import create_prompt
from repository.optimized_prompts import create_optimized_prompt

from repository.validation import create_validation
from schema.optimized_prompts import OptimizedPromptCreate
from schema.orchestration import OrchestrationUpdate
from schema.prompts import PromptCreate
from schema.audit import AuditCreate

from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult
from schema.validation import ValidationCreate

logger = logging.getLogger("orchestration_pipeline")

@dataclass
class RunOrchestrator:
    run_id: int
    user_id: str # do we need this? perhap
    prompt_id: int | None = None
    status: str = "Pending"
    rate_per_mtok: float
    final_optimized_prompt_id: int | None = None
    finished_at: datetime | None = None

    ##TODO: i need to pass in the db...
    #TODO: we need to make sure the status changes at the correct time lol?
    #TODO: make the update to actually get the correct format...

    def __init__(self, prompt: str):
        ## all it has to do it be related to a user?
        try:
            promptFormatted : PromptCreate = structure_response(prompt)
            savedPrompt = create_prompt(promptFormatted)

            self.prompt_id = savedPrompt["prompt_id"]
            self = create_orchestration(self)
            
        except Exception as e:
            logger.log(logging.ERROR, f"failed to save prompt: {e}")

        ### I HAD THIS but i think creating one orchestration should solve allat
        # self.status = "pending"
        # # might need to reformat this later...
        # self.started_at = datetime.now()
        # self.updated_at = self.started_at

    # idk if these needs a return. prob not
    def saveAudit(self, audit: AuditResult):
        try:
            auditFormatted : AuditCreate = structure_response(audit)
            savedAudit = create_audit(auditFormatted)

            self.audit_id = savedAudit["audit_id"]
            update_orchestration(self)
        except Exception as e:
            logger.log(logging.ERROR, f"failed to save audit: {e}")

    def saveOptimization(self, optimization: OptimizationResult):
        try:
            optimizationFormatted : OptimizedPromptCreate = structure_response(optimization)
            savedOptimization = create_optimized_prompt(optimizationFormatted)

            # update_orchestration(self)
        except Exception as e:
            logger.log(logging.ERROR, f"failed to save optimization: {e}")

    def saveValidation(self, validation: ValidationResult):
        try:
            validationFormated : ValidationCreate = structure_response(validation)
            create_validation(validationFormated)

        except Exception as e:
            logger.log(logging.ERROR, f"failed to save validation: {e}")

    def finishJob(self, result: OrchestrationResult):
        try:
            orchestrationFormated : OrchestrationUpdate = structure_response(result)
            update_orchestration(orchestrationFormated)

        except Exception as e:
            logger.log(logging.ERROR, f"failed to save resulting: {e}")

## helpar (PLACEHOLDER i don't feel like implementing it rn lol)
def structure_response(meow: str):
    pass