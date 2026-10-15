from fastapi import APIRouter, Depends

from auth import current_user

from routes.optimized_prompts import router as optimized_prompts_router
from routes.prompts import router as prompts_router
from routes.users import router as users_router
from routes.prompt_w_optimized import router as prompt_w_optimized_router

# every route mounted here requires a valid clerk token
router = APIRouter(dependencies=[Depends(current_user)])
router.include_router(users_router, prefix="/users", tags=["users"])
router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
router.include_router(optimized_prompts_router, prefix="/optimized-prompts", tags=["optimized-prompts"])
router.include_router(prompt_w_optimized_router, prefix="/prompt-w-optimized", tags=["prompt-w-optimized"])
