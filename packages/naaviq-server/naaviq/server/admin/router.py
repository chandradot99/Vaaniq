from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.admin.dependencies import CurrentUser, require_owner
from naaviq.server.admin.schemas import (
    PlatformConfigResponse,
    ProviderSchema,
    UpsertPlatformConfigRequest,
)
from naaviq.server.admin.service import AdminService, get_all_schemas
from naaviq.server.core.database import get_db

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/platform-configs/schemas", response_model=list[ProviderSchema])
async def list_schemas(
    _: CurrentUser = Depends(require_owner),
) -> list[ProviderSchema]:
    """Return field definitions for all supported providers."""
    return get_all_schemas()


@router.get("/platform-configs", response_model=list[PlatformConfigResponse])
async def list_configs(
    _: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> list[PlatformConfigResponse]:
    """Return all saved platform configs (no credentials — config fields only)."""
    return await AdminService(db).list_configs()


@router.put(
    "/platform-configs/{provider}",
    response_model=PlatformConfigResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_config(
    provider: str,
    body: UpsertPlatformConfigRequest,
    _: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> PlatformConfigResponse:
    """Create or update a platform config for the given provider."""
    return await AdminService(db).upsert(provider, body)


@router.delete("/platform-configs/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    provider: str,
    _: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a platform config."""
    await AdminService(db).delete(provider)
