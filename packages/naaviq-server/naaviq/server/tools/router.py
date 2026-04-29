from fastapi import APIRouter, Depends
from naaviq.server.auth.dependencies import CurrentUser, get_current_user
from naaviq.server.core.schemas import CustomModel

router = APIRouter(prefix="/v1/tools", tags=["tools"])


class ToolInfo(CustomModel):
    name: str
    description: str
    input_schema: dict
    required_integration: str | None


@router.get("", response_model=list[ToolInfo])
async def list_tools(
    _: CurrentUser = Depends(get_current_user),
) -> list[ToolInfo]:
    """Return all tools available in the TOOL_REGISTRY."""
    from naaviq.tools.registry import TOOL_REGISTRY

    return [
        ToolInfo(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            required_integration=tool.required_integration,
        )
        for tool in TOOL_REGISTRY.values()
    ]
