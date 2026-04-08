from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.auth.dependencies import CurrentUser, get_current_user
from vaaniq.server.core.database import get_db
from vaaniq.server.integrations.exceptions import IntegrationNotFound
from vaaniq.server.integrations.repository import IntegrationRepository
from vaaniq.server.models.integration import Integration


async def valid_integration(
    integration_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Integration:
    """Fetch and validate that integration_id exists and belongs to the current org."""
    integration = await IntegrationRepository(db).get_by_id(integration_id)
    if not integration or integration.org_id != current.org_id:
        raise IntegrationNotFound()
    return integration
