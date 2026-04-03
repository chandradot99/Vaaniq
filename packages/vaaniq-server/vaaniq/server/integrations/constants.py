# PROVIDERS registry lives in vaaniq-tools so standalone developers can use it
# without installing vaaniq-server. Import and re-export here for server use.
from vaaniq.tools.providers import PROVIDERS, SUPPORTED_PROVIDERS, TESTABLE_PROVIDERS

# Server-specific alias (kept for clarity in service.py)
_TESTABLE_PROVIDERS = TESTABLE_PROVIDERS

__all__ = ["PROVIDERS", "SUPPORTED_PROVIDERS", "TESTABLE_PROVIDERS", "_TESTABLE_PROVIDERS"]
