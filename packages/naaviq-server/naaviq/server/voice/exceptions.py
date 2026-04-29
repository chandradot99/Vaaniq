class VoiceError(Exception):
    """Base for all voice errors."""


class VoiceSessionError(VoiceError):
    """Base for voice session setup errors."""


class PhoneNumberNotFound(VoiceError):
    def __init__(self, number_id: str = "") -> None:
        super().__init__(f"Phone number '{number_id}' not found.")
        self.number_id = number_id


class PhoneNumberNameConflict(VoiceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"A pipeline named '{name}' already exists in this org.")
        self.name = name


class PhoneNumberAccessDenied(VoiceError):
    """Raised when a phone number belongs to a different org."""


class PhoneNumberAlreadyExists(VoiceError):
    def __init__(self, number: str) -> None:
        super().__init__(f"Phone number '{number}' is already registered.")
        self.number = number


class TwilioCredentialsMissing(VoiceError):
    """Raised when the org has no Twilio credentials configured."""


class OutboundCallFailed(VoiceError):
    """Raised when the Twilio REST API call to create a call fails."""


class SessionNotFound(VoiceSessionError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Voice session '{session_id}' not found.")
        self.session_id = session_id


class AgentNotConfigured(VoiceSessionError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"Agent '{agent_id}' has no graph_config — publish the agent before connecting.")
        self.agent_id = agent_id


class TwilioHandshakeError(VoiceSessionError):
    """Raised when the Twilio Media Streams handshake doesn't complete as expected."""
