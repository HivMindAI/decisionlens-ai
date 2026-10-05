from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.models.decisions import DecisionContext, DecisionFocus, NextStepAction

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 120.0
PROVIDER_NAME = "openai_compatible"


class DecisionBriefProvider(Protocol):
    name: str
    model: str

    async def generate(self, context: DecisionContext) -> str: ...


class ProviderFailure(Exception):
    """A provider failure represented only by a non-secret application code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProviderSetup:
    provider: DecisionBriefProvider | None
    fallback_reason: str | None = None
    provider_name: str | None = None
    model: str | None = None


class OpenAICompatibleDecisionBriefProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = _chat_completions_endpoint(base_url)
        self._api_key = api_key
        self.model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def generate(self, context: DecisionContext) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {
                    "role": "user",
                    "content": (
                        "Create the decision brief from this allowlisted deterministic "
                        "context only:\n"
                        + json.dumps(
                            context.model_dump(mode="json"),
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderFailure("provider_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderFailure("provider_http_error") from exc
        except httpx.RequestError as exc:
            raise ProviderFailure("provider_connection_error") from exc

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise ProviderFailure("malformed_provider_payload") from exc

        if not isinstance(response_payload, dict):
            raise ProviderFailure("malformed_provider_payload")
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderFailure("malformed_provider_payload")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderFailure("malformed_provider_payload")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ProviderFailure("malformed_provider_payload")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderFailure("missing_provider_content")
        return content


def provider_setup_from_environment() -> ProviderSetup:
    enabled_value = os.getenv("DECISIONLENS_LLM_ENABLED")
    enabled = _parse_enabled(enabled_value)
    if enabled is None:
        return ProviderSetup(
            provider=None,
            fallback_reason="provider_configuration_invalid",
            provider_name=PROVIDER_NAME,
        )
    if not enabled:
        return ProviderSetup(
            provider=None,
            fallback_reason="llm_not_configured",
        )

    base_url = os.getenv("DECISIONLENS_LLM_BASE_URL", "").strip()
    api_key = os.getenv("DECISIONLENS_LLM_API_KEY", "").strip()
    model = os.getenv("DECISIONLENS_LLM_MODEL", "").strip()
    timeout_value = os.getenv(
        "DECISIONLENS_LLM_TIMEOUT_SECONDS",
        str(DEFAULT_TIMEOUT_SECONDS),
    ).strip()

    try:
        timeout_seconds = float(timeout_value)
    except ValueError:
        timeout_seconds = math.nan

    if (
        not _valid_base_url(base_url)
        or not api_key
        or not model
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > MAX_TIMEOUT_SECONDS
    ):
        return ProviderSetup(
            provider=None,
            fallback_reason="provider_configuration_invalid",
            provider_name=PROVIDER_NAME,
            model=model or None,
        )

    provider = OpenAICompatibleDecisionBriefProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    return ProviderSetup(
        provider=provider,
        provider_name=provider.name,
        model=provider.model,
    )


def _parse_enabled(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _valid_base_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _system_prompt() -> str:
    focus_values = ", ".join(item.value for item in DecisionFocus)
    action_values = ", ".join(item.value for item in NextStepAction)
    return (
        "You produce one evidence-backed business Decision Brief. Use only the supplied "
        "deterministic context. Never calculate business values, invent evidence, make "
        "causal claims, create numeric recommendations, or use outside knowledge. The "
        "headline and reasoning must be qualitative and must contain no numeric business "
        "claims; evidence identifiers such as E1 are allowed. Cite one to five existing "
        "evidence IDs, preferring at least two when supported. Select only an allowed focus "
        f"({focus_values}) and next_step ({action_values}). Return only a JSON object with "
        "exactly these keys: focus, headline, reasoning, evidence_ids, next_step."
    )
