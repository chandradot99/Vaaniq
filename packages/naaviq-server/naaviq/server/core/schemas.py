from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, model_serializer


def _fmt_dt(dt: datetime) -> str:
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


class CustomModel(BaseModel):
    """
    Global base model for all Naaviq schemas.
    - Serializes all datetime fields to UTC ISO format with explicit timezone.
    - Allows population by field name (not just alias).
    """

    model_config = ConfigDict(populate_by_name=True)

    @model_serializer(mode="wrap")
    def _serialize(self, handler: Callable[["CustomModel"], dict[str, Any]]) -> dict[str, Any]:
        data = handler(self)
        return {k: _fmt_dt(v) if isinstance(v, datetime) else v for k, v in data.items()}
