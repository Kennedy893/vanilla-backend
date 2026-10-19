from fastapi import APIRouter
from app.api.endpoints import auth, farm, location, lot, organization, transfer

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(lot.router)
api_router.include_router(farm.router)
api_router.include_router(location.router)
api_router.include_router(organization.router)
api_router.include_router(transfer.router)