from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str
    description: str

    def __init__(self, config: dict, org_keys: dict) -> None:
        self.config = config
        self.org_keys = org_keys

    @abstractmethod
    async def run(self, input: dict[str, Any]) -> Any:
        raise NotImplementedError
