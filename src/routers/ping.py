# ping.py is the health check endpoint for the API

from fastapi import APIRouter
from sqlalchemy import text

from ..dependencies import DatabaseDep, PineconeDep, SettingsDep
from ..schemas.api.health import HealthResponse, ServiceStatus

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health(settings: SettingsDep, database: DatabaseDep, pinecone: PineconeDep) -> HealthResponse:
    """
    Health check — verifies Postgres + Pinecone connectivity.

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

    # Pinecone — one stats call proves the connection works and shows how much is indexed
    try:
        vector_count = pinecone.index.describe_index_stats().total_vector_count
        services["pinecone"] = ServiceStatus(status="healthy", message=f"{vector_count} chunks indexed")
    except Exception as e:
        services["pinecone"] = ServiceStatus(status="unhealthy", message=str(e))
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version="0.1.0",
        environment="dev",
        service_name="rag-api",
        services=services,
    )
