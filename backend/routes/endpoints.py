from fastapi import APIRouter, Depends

from auth import current_user

from routes.optimized_prompts import router as optimized_prompts_router
from routes.prompts import router as prompts_router
from routes.guest_prompts import router as guest_prompts_router
from routes.users import router as users_router
from routes.prompt_w_optimized import router as prompt_w_optimized_router

# Existing user-specific routes require a valid Clerk token.
router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(current_user)])
protected_router.include_router(users_router, prefix="/users", tags=["users"])
protected_router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
protected_router.include_router(optimized_prompts_router, prefix="/optimized-prompts", tags=["optimized-prompts"])
protected_router.include_router(prompt_w_optimized_router, prefix="/prompt-w-optimized", tags=["prompt-w-optimized"])

router.include_router(protected_router)
router.include_router(guest_prompts_router, prefix="/prompts", tags=["prompts"])
