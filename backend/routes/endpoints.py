from fastapi import APIRouter, Depends

from auth import current_user

from routes.optimized_prompts import router as optimized_prompts_router
from routes.prompts import router as prompts_router
# from routes.users import router as users_router
from routes.prompt_w_optimized import router as prompt_w_optimized_router
from routes.orchestrator import router as ochestrator_router
from routes.audit import router as audit_router
from routes.context import router as context_router
from routes.validation import router as validation_router


router = APIRouter()
# router.include_router(users_router, prefix="/users", tags=["users"], dependencies=[Depends(current_user)])
router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
router.include_router(optimized_prompts_router, prefix="/optimized-prompts", tags=["optimized-prompts"])
router.include_router(prompt_w_optimized_router, prefix="/prompt-w-optimized", tags=["prompt-w-optimized"])
# this gets depends bc it doesn't have rls in it
router.include_router(ochestrator_router, prefix="/orchestrator", tags=["orchestrator"], dependencies=[Depends(current_user)])
router.include_router(audit_router, prefix="/audits", tags=["audits"])
router.include_router(context_router, prefix="/contexts", tags=["contexts"])
router.include_router(validation_router, prefix="/validations", tags=["validations"])