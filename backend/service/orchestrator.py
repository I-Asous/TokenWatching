from agents.orchestrator import runPipeline 
from schema.orchestrator import OrchestrationResult

def orchestrator(prompt: str, target: str) -> OrchestrationResult: # idk what target is!
    try:
        result = runPipeline(prompt, target)
    except Exception as e:
        raise RuntimeError(f"Orchestration error: {str(e)}")
    return result