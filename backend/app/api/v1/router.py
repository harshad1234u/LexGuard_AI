from fastapi import APIRouter

from app.api.v1 import routes_analysis, routes_documents, routes_health, routes_qa

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(routes_health.router)
api_router.include_router(routes_documents.router)
api_router.include_router(routes_analysis.documents_router)
api_router.include_router(routes_analysis.analysis_router)
api_router.include_router(routes_qa.router)
