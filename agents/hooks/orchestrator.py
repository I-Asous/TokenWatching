from typing import TYPE_CHECKING

from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult
from agents.validator import ValidationResult

# this is because we import hooks in orchestrator, but also import orchestration result here...
# and since one is unfinished, it crashes everything
# so this makes it so that the app doesn't crash at runtime but that type checking still works in vs code...
# TODO: and im just keeping it for now so in the future we can make all the results jsut be in one folder instead of individual folders.
if TYPE_CHECKING:
    from agents.orchestrator import OrchestrationResult

class OrchestrationHooks:
    # USE WHEN UPDATING WHERE AN ORCHESTRATION IS CURRENTLY AT (auditing, optimizing, etc)
    def updateStage(self, status: str): pass

    # USE WHEN SAVING THE DATA OF AN ORCHESTRATION RESULT
    def saveAudit(self, result: AuditResult): pass
    def saveOptimization(self, result: OptimizationResult): pass
    def saveValidation(self, result: ValidationResult): pass

    # USE WHEN THE ORCHESTRATOR IS DONE AND REACHED A CONCLUSION
    # this is in quotes bc of type checking t_t
    def finishJob(self, result: "OrchestrationResult"): pass
