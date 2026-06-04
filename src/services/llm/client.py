"""Anthropic LLM client with retry and error handling."""

import asyncio
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MODEL_ID = "claude-sonnet-4-6"
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 2.0


class LLMClientError(Exception):
    """Raised when the LLM client encounters an unrecoverable error."""


class LLMClient:
    """Thin wrapper around anthropic.Anthropic with retry logic."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        # api_key=None lets the SDK pick up ANTHROPIC_API_KEY from the environment
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Call the Anthropic Messages API synchronously with retry.

        Args:
            system: System prompt text.
            user: User message text.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0.0–1.0).

        Returns:
            The assistant response text.

        Raises:
            LLMClientError: After MAX_RETRIES failed attempts.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 2):  # 1, 2, 3 — gives MAX_RETRIES retries
            try:
                message = self._client.messages.create(
                    model=MODEL_ID,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return message.content[0].text
            except anthropic.RateLimitError as exc:
                last_exc = exc
                logger.warning(
                    "Rate limit hit on attempt %d/%d. Retrying in %ss.",
                    attempt,
                    MAX_RETRIES + 1,
                    RETRY_DELAY_SECONDS,
                )
                if attempt <= MAX_RETRIES:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
            except anthropic.APIStatusError as exc:
                last_exc = exc
                logger.error(
                    "API status error %s on attempt %d/%d: %s",
                    exc.status_code,
                    attempt,
                    MAX_RETRIES + 1,
                    exc.message,
                )
                if attempt <= MAX_RETRIES:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)
            except anthropic.APIConnectionError as exc:
                last_exc = exc
                logger.error("Connection error on attempt %d/%d.", attempt, MAX_RETRIES + 1)
                if attempt <= MAX_RETRIES:
                    import time
                    time.sleep(RETRY_DELAY_SECONDS)

        raise LLMClientError(
            f"LLM request failed after {MAX_RETRIES + 1} attempts."
        ) from last_exc

    async def complete_async(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Async wrapper — runs the blocking call in a thread-pool executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.complete(system, user, max_tokens, temperature),
        )


# Module-level default instance (picks up ANTHROPIC_API_KEY from environment)
_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    """Return (and lazily create) the module-level default LLMClient."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
