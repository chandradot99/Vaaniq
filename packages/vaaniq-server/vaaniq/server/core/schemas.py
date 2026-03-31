from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict


def datetime_to_utc_str(dt: datetime) -> str:
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


class CustomModel(BaseModel):
    """
    Global base model for all Vaaniq schemas.
    - Serializes all datetime fields to UTC ISO format with explicit timezone.
    - Allows population by field name (not just alias).
    """

    model_config = ConfigDict(
        json_encoders={datetime: datetime_to_utc_str},
        populate_by_name=True,
    )
