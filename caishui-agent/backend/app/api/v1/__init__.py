from fastapi import APIRouter
from app.api.v1 import auth, users, companies, risk_indicators, miniapp, llm_config

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(companies.router)
api_router.include_router(risk_indicators.router)
api_router.include_router(miniapp.router)
api_router.include_router(llm_config.router)
