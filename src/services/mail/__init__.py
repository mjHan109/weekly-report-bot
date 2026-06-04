"""Mail service package.

Exports the public surface used by the rest of the application:

  TokenManager   — delegated token lifecycle
  GraphClient    — Microsoft Graph HTTP client with retry + circuit breaker
  DraftService   — builds and persists Outlook draft messages
  SendService    — triple-gate verified mail send
"""

from .token_manager import TokenManager
from .graph_client import GraphClient
from .draft_service import DraftService
from .send_service import SendService

__all__ = [
    "TokenManager",
    "GraphClient",
    "DraftService",
    "SendService",
]
