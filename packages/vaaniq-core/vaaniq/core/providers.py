from abc import ABC, abstractmethod


class BaseLLM(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict], **kwargs) -> str:
        raise NotImplementedError


class BaseSTT(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes) -> str:
        raise NotImplementedError


class BaseTTS(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        raise NotImplementedError
