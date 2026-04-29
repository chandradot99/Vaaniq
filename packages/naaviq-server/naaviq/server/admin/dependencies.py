from fastapi import Depends
from naaviq.server.admin.exceptions import AdminOnly
from naaviq.server.auth.dependencies import CurrentUser, get_current_user


async def require_owner(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Only org owners can access admin endpoints."""
    if current.role != "owner":
        raise AdminOnly()
    return current
