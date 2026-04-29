# PROVIDERS registry lives in naaviq-tools so standalone developers can use it
# without installing naaviq-server. Import and re-export here for server use.
from naaviq.tools.providers import PROVIDERS, SUPPORTED_PROVIDERS, TESTABLE_PROVIDERS

# Server-specific alias (kept for clarity in service.py)
_TESTABLE_PROVIDERS = TESTABLE_PROVIDERS

__all__ = ["PROVIDERS", "SUPPORTED_PROVIDERS", "TESTABLE_PROVIDERS", "_TESTABLE_PROVIDERS"]
