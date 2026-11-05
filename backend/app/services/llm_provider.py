import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections.abc import Sequence
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """Raised when the configured model cannot produce a response."""


class LLMProvider(Protocol):
    async def ainvoke(
        self, messages: Sequence[BaseMessage], tools: Sequence[BaseTool]
    ) -> AIMessage: ...


class GroqProvider:
    def __init__(self, settings: Settings, model: BaseChatModel | None = None):
        self.settings = settings
        self._model = model

    def _get_model(self) -> BaseChatModel:
        if self._model is None:
            if self.settings.groq_api_key is None:
                raise LLMProviderError("GROQ_API_KEY is not configured")
            model_kwargs = {"include_reasoning": False}
            self._model = ChatGroq(
                api_key=self.settings.groq_api_key.get_secret_value(),
                model=self.settings.groq_model,
                temperature=0,
                timeout=self.settings.groq_timeout_seconds,
                max_retries=0,
                max_tokens=self.settings.groq_max_output_tokens,
                reasoning_effort=self.settings.groq_reasoning_effort,
                model_kwargs=model_kwargs,
            )
        return self._model

    async def ainvoke(
        self, messages: Sequence[BaseMessage], tools: Sequence[BaseTool]
    ) -> AIMessage:
        for attempt in range(self.settings.groq_max_retries + 1):
            try:
                bound_model = self._get_model().bind_tools(tools, tool_choice="auto")
                response = await bound_model.ainvoke(list(messages))
                if not isinstance(response, AIMessage):
                    raise LLMProviderError("Groq provider returned an unexpected response type")
                return response
            except Exception as exc:
                is_last_attempt = attempt >= self.settings.groq_max_retries
                if not _is_rate_limit_error(exc) or is_last_attempt:
                    logger.exception(
                        "Groq provider request failed; model=%s tool_count=%d attempts=%d",
                        self.settings.groq_model,
                        len(tools),
                        attempt + 1,
                    )
                    raise LLMProviderError("Groq provider request failed") from exc

                delay = _retry_delay(exc, attempt, self.settings)
                logger.warning(
                    "Groq rate limit encountered; retrying attempt=%d/%d delay_seconds=%.2f",
                    attempt + 1,
                    self.settings.groq_max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)

        raise LLMProviderError("Groq provider request failed")


def _is_rate_limit_error(error: Exception) -> bool:
    current: BaseException | None = error
    while current is not None:
        status_code = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        if status_code == 429 or response_status == 429:
            return True
        if "ratelimit" in type(current).__name__.lower() or "rate_limit" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def _retry_after_seconds(error: Exception) -> float | None:
    current: BaseException | None = error
    while current is not None:
        response = getattr(current, "response", None)
        headers = getattr(response, "headers", None) or getattr(current, "headers", None)
        if headers:
            value = headers.get("retry-after") or headers.get("Retry-After")
            if value:
                try:
                    return max(0.0, float(value))
                except (TypeError, ValueError):
                    try:
                        retry_at = parsedate_to_datetime(value)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=timezone.utc)
                        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        pass
        current = current.__cause__ or current.__context__
    match = re.search(r"try again in\s+(\d+(?:\.\d+)?)s", str(error), flags=re.IGNORECASE)
    if match:
        return max(0.0, float(match.group(1)))
    return None


def _retry_delay(error: Exception, attempt: int, settings: Settings) -> float:
    retry_after = _retry_after_seconds(error)
    if retry_after is not None:
        return min(settings.groq_retry_after_max_seconds, retry_after)
    exponential = min(
        settings.groq_retry_max_seconds,
        settings.groq_retry_base_seconds * (2**attempt),
    )
    return exponential * random.uniform(0.8, 1.2)

