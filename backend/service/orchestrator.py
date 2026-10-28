# TODO: so many imports can we like not...

# from agents.orchestrator import runPipeline 
# from schema.orchestrator import OrchestrationResult
from dataclasses import dataclass, field

from supabase import Client

from agents.hooks.orchestrator import OrchestrationHooks
from agents.orchestrator import OrchestrationResult, runPipeline
from agents.validator import ValidationResult
from repository.client import get_supabase
from repository.llm_call import create_llm_call
from repository.orchestration import create_orchestration, update_orchestration, update_orchestration_status
from repository.prompts import create_prompt
from repository.optimized_prompts import create_optimized_prompt

from repository.validation import create_validation
from schema.llm_call import LlmCall
from schema.optimized_prompts import OptimizedPromptInsert
from schema.orchestration import OrchestrationInsert, OrchestrationUpdate
from schema.prompts import PromptInsert
from service.audit import save_audit
from service.structure_response import structure_response

from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult
from schema.validation import ValidationInsert


@dataclass
class RunOrchestrator(OrchestrationHooks):
    user_id: str 
    prompt: str
    target: str
    db: Client = field(default_factory=get_supabase, init=False)
    run_id: int | None = field(default=None, init=False)
    status: str = field(default="pending", init=False)
    last_optimized_prompt_id: int | None = field(default=None, init=False)
    last_rejected_validation_id: int | None = field(default=None, init=False)
    final_optimized_prompt_id: int | None = field(default=None, init=False)

    # before we can run the pipeline, we save anything necessary beforehand and then we can continue (and actually run it!)
    def execute(self) -> OrchestrationResult:
        promptFormatted : PromptInsert = PromptInsert(user_id=self.user_id, txt_prompt=self.prompt, target=self.target)
        savedPrompt = create_prompt(self.db, promptFormatted)

        savedRun = create_orchestration(self.db, OrchestrationInsert(user_id=self.user_id, prompt_id=savedPrompt[0]["prompt_id"]))
        self.run_id = savedRun[0]["run_id"]

        try:
            return runPipeline(self.prompt, self.target, hook=self)
        except Exception as e:
            update_orchestration(self.db, self.run_id, OrchestrationUpdate(
                status="failed",
                error_stage=self.status if self.status != "pending" else "other",
                error_message=str(e)))
            raise RuntimeError(f"Orchestration error: {str(e)}") from e

    # allows something else (ex. orchestrator, agent) to update what stage they're currently at
    # this is done bc the other functions here (saveAudit, etc), don't necessarily mean they went
    # to the next stage. it is only the function that calls the agent in orchestrator that does it
    def updateStage(self, status: str):
        self.status = status
        update_orchestration_status(self.db, self.run_id, status)

    # calls repository to save an audit
    def saveAudit(self, audit: AuditResult):
        save_audit(self.db, self.user_id, self.run_id, audit)

    # calls repository to save an optimization
    def saveOptimization(self, optimization: OptimizationResult):
        optimizationFormatted : OptimizedPromptInsert = structure_response(optimization, self.user_id, feedback_validation_id=self.last_rejected_validation_id)
        savedOptimization = create_optimized_prompt(self.db, optimizationFormatted)
        self.last_optimized_prompt_id = savedOptimization[0]["optimized_prompt_id"]

    # calls repository to save a validation
    def saveValidation(self, validation: ValidationResult):
        validationFormated : ValidationInsert = structure_response(validation, self.user_id, optimized_prompt_id=self.last_optimized_prompt_id)
        savedValidation = create_validation(self.db, validationFormated)

        if validation.passed:
            self.final_optimized_prompt_id = self.last_optimized_prompt_id
        else:
            self.last_rejected_validation_id = savedValidation[0]["validation_id"]

    # save an llm call (unsure how it will be set up so needs fine tuning)
    def saveLLMCall(self, result: LlmCall):
        create_llm_call(result)

    # orchestrator is done with it's job and we can update it with any necessary information
    def finishJob(self, result: OrchestrationResult):
        orchestrationFormated : OrchestrationUpdate = structure_response(result, self.user_id, final_optimized_prompt_id=self.final_optimized_prompt_id)
        update_orchestration(self.db, self.run_id, orchestrationFormated)