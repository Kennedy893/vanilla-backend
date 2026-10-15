from fastapi import APIRouter
from app.api.endpoints import auth, farm, lot

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(lot.router)
api_router.include_router(farm.router)