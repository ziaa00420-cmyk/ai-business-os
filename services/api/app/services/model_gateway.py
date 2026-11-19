"""The one place the API calls a language model.

Every call is recorded in model_calls (model, tokens, latency, stop reason) so
cost per business and per task is visible from day one. Swapping providers or
adding Langfuse tracing later means changing this module only.
"""

import time
from typing import TypeVar
from uuid import UUID

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ModelCall

T = TypeVar("T", bound=BaseModel)


class ModelUnavailable(RuntimeError):
    """No API key is configured, so callers should use their non-AI fallback."""


class ModelRefused(RuntimeError):
    pass


_client: anthropic.Anthropic | None = None


def model_available() -> bool:
    return bool(get_settings().anthropic_api_key)


def _get_client() -> anthropic.Anthropic:
    global _client
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ModelUnavailable("ANTHROPIC_API_KEY is not set")
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2)
    return _client


def structured_call(
    session: Session,
    *,
    business_id: UUID,
    task_id: UUID | None,
    purpose: str,
    system: str,
    user_content: str,
    output_type: type[T],
    model: str | None = None,
    max_tokens: int = 16000,
) -> T:
    """Ask the model for output that validates against `output_type`."""
    client = _get_client()
    model = model or get_settings().agent_model
    record = ModelCall(business_id=business_id, task_id=task_id, model=model, purpose=purpose)
    started = time.monotonic()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            output_format=output_type,
        )
        record.input_tokens = response.usage.input_tokens
        record.output_tokens = response.usage.output_tokens
        record.stop_reason = response.stop_reason
        if response.stop_reason == "refusal":
            raise ModelRefused("The model declined this request")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Model output was cut off at max_tokens")
        parsed = response.parsed_output
        if parsed is None:
            raise RuntimeError("Model returned no parsable output")
        return parsed
    except Exception as exc:
        record.error = f"{type(exc).__name__}: {exc}"[:2000]
        raise
    finally:
        record.latency_ms = int((time.monotonic() - started) * 1000)
        session.add(record)
        session.flush()
