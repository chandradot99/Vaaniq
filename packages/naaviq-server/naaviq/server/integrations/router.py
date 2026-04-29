from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from naaviq.server.auth.dependencies import CurrentUser, get_current_user
from naaviq.server.core.database import get_db
from naaviq.server.integrations.dependencies import valid_integration
from naaviq.server.integrations.oauth import oauth_router
from naaviq.server.integrations.schemas import (
    CreateIntegrationRequest,
    IntegrationResponse,
    TestIntegrationResponse,
)
from naaviq.server.integrations.service import IntegrationService
from naaviq.server.models.integration import Integration

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])
router.include_router(oauth_router)


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: CreateIntegrationRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    return await IntegrationService(db).create(current.org_id, body)


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IntegrationResponse]:
    return await IntegrationService(db).list(current.org_id)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    current: CurrentUser = Depends(get_current_user),
    integration: Integration = Depends(valid_integration),
    db: AsyncSession = Depends(get_db),
) -> None:
    await IntegrationService(db).delete(integration.id, current.org_id)


@router.post("/{integration_id}/test", response_model=TestIntegrationResponse)
async def test_integration(
    current: CurrentUser = Depends(get_current_user),
    integration: Integration = Depends(valid_integration),
    db: AsyncSession = Depends(get_db),
) -> TestIntegrationResponse:
    return await IntegrationService(db).test(integration.id, current.org_id)
