from abc import ABC, abstractmethod
from vaaniq.core.state import SessionState


class BaseNode(ABC):
    def __init__(self, config: dict, org_keys: dict) -> None:
        self.config = config
        self.org_keys = org_keys

    @abstractmethod
    async def __call__(self, state: SessionState) -> dict:
        raise NotImplementedError
