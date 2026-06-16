from fastapi import APIRouter
from sqlalchemy import text
from ..dependencies import DatabaseDep, OpenSearchDep, SettingsDep
from ..schemas.api.health import HealthResponse, ServiceStatus

router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health(settings: SettingsDep, database: DatabaseDep, opensearch_client: OpenSearchDep) -> HealthResponse:
    """Comprehensive health check endpoint for monitoring and load balancer probes.

    :returns: Service health status with version and connectivity checks
    :rtype: HealthResponse
    """
    services = {}
    overall_status = "ok"
    
    

    