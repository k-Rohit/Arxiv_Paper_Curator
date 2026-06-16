# ping.py is the health check endpoing for the API

from fastapi import APIRouter
from sqlalchemy import text
from ..dependencies import DatabaseDep, OpenSearchDep, SettingsDep
from ..schemas.api.health import HealthResponse, ServiceStatus

router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health(settings: SettingsDep, database: DatabaseDep, opensearch_client: OpenSearchDep) -> HealthResponse:
    """
    Health check — verifies Postgres + OpenSearch connectivity.

    :returns: Service health status with version and connectivity checks
    :rtype: HealthResponse
    """
    services = {}
    overall_status = "ok"
    
    # Postgres
    try:
        with database.get_session() as session:
            session.execute(text("SELECT 1"))
        services["postgres"] = ServiceStatus(status="healthy", message="Connected")
    except Exception as e:
        services["postgres"] = ServiceStatus(status="unhealthy", message=str(e))
        overall_status = "degraded"
    
    # Opensearch 
    try:
        if opensearch_client.health_check():
            stats = opensearch_client.get_index_stats()
            services["opensearch"] = ServiceStatus(
                status="healthy",
                message=f"{stats.get('document_count', 0)} documents indexed"
            )
        else:
            services["opensearch"] = ServiceStatus(status="unhealthy", message="Not responding")
            overall_status = "degraded"
    except Exception as e:
        services["opensearch"] = ServiceStatus(status="unhealthy", message=str(e))
        overall_status = "degraded"
        
    return HealthResponse(
    status=overall_status,
    version="0.1.0",
    environment="dev",
    service_name="rag-api",
    )


    
        
    
    
    
    
    
    
    
    


    