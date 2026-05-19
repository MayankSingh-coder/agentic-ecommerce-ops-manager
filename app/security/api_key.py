from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

PUBLIC_PATH_SUFFIXES = {
    "/health",
    "/contracts",
}


async def require_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> None:
    if any(request.url.path.endswith(path_suffix) for path_suffix in PUBLIC_PATH_SUFFIXES):
        return
    if not settings.ecommerce_ops_api_key:
        return
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if api_key != settings.ecommerce_ops_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
