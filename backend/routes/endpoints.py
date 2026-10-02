from fastapi import APIRouter

from routes.optimized_prompts import router as optimized_prompts_router
from routes.prompts import router as prompts_router
from routes.users import router as users_router

router = APIRouter()
router.include_router(users_router)
router.include_router(prompts_router)
router.include_router(optimized_prompts_router)
