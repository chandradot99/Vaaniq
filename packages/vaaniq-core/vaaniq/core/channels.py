from abc import ABC, abstractmethod
from vaaniq.core.state import SessionState


class BaseChannel(ABC):
    @abstractmethod
    async def send(self, state: SessionState, message: str) -> None:
        raise NotImplementedError
