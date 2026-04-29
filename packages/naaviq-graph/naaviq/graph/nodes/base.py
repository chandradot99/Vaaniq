from abc import ABC, abstractmethod

from naaviq.core.state import SessionState

# State keys that nodes must never write to via save_response_to / set_variable.
# Writing to these could silently corrupt session lifecycle or history.
PROTECTED_STATE_KEYS: frozenset[str] = frozenset({
    "session_id", "agent_id", "org_id", "channel", "user_id",
    "messages", "tool_calls", "session_ended", "transfer_initiated",
    "transfer_to", "whisper_message", "start_time", "end_time",
    "duration_seconds", "current_node",
})


class BaseNode(ABC):
    def __init__(self, config: dict, org_keys: dict) -> None:
        self.config = config
        self.org_keys = org_keys

    @abstractmethod
    async def __call__(self, state: SessionState) -> dict:
        raise NotImplementedError
