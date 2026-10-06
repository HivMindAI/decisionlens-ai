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

    async def generate(
        self,
        context: DecisionContext,
        *,
        correction: str | None = None,
    ) -> str: ...


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
        self._structured_outputs_supported = True

    async def generate(
        self,
        context: DecisionContext,
        *,
        correction: str | None = None,
    ) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                use_structured_outputs = self._structured_outputs_supported
                payload = _provider_payload(
                    context,
                    model=self.model,
                    correction=correction,
                    use_structured_outputs=use_structured_outputs,
                )
                response = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                # Compatibility is transport-only: JSON Object mode still flows through
                # every application validator in decisions.py.
                if use_structured_outputs and _json_schema_is_unsupported(response):
                    self._structured_outputs_supported = False
                    response = await client.post(
                        self._endpoint,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=_provider_payload(
                            context,
                            model=self.model,
                            correction=correction,
                            use_structured_outputs=False,
                        ),
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


def build_decision_brief_schema(context: DecisionContext) -> dict[str, object]:
    evidence_ids = [item.id for item in context.evidence]
    return {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "enum": [item.value for item in DecisionFocus],
            },
            "headline": {"type": "string"},
            "reasoning": {"type": "string"},
            "evidence_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": evidence_ids,
                },
                "minItems": 1,
                "maxItems": 5,
            },
            "next_step": {
                "type": "string",
                "enum": [item.value for item in NextStepAction],
            },
        },
        "required": [
            "focus",
            "headline",
            "reasoning",
            "evidence_ids",
            "next_step",
        ],
        "additionalProperties": False,
    }


def _provider_payload(
    context: DecisionContext,
    *,
    model: str,
    correction: str | None,
    use_structured_outputs: bool,
) -> dict[str, object]:
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": _context_prompt(context)},
    ]
    if correction is not None:
        messages.append(
            {
                "role": "user",
                "content": _corrective_prompt(correction),
            }
        )

    response_format: dict[str, object]
    if use_structured_outputs:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "decision_brief",
                "strict": True,
                "schema": build_decision_brief_schema(context),
            },
        }
    else:
        response_format = {"type": "json_object"}

    return {
        "model": model,
        "temperature": 0,
        "response_format": response_format,
        "messages": messages,
    }


def _json_schema_is_unsupported(response: httpx.Response) -> bool:
    if response.status_code not in {400, 422}:
        return False

    message = response.text.lower()
    identifies_schema = any(
        marker in message
        for marker in ("json_schema", "response_format", "structured output")
    )
    identifies_unsupported = any(
        marker in message
        for marker in ("not supported", "unsupported", "does not support")
    )
    return identifies_schema and identifies_unsupported


def _system_prompt() -> str:
    return (
        "Return one evidence-backed Decision Brief as JSON only. Use only the supplied "
        "deterministic context. Choose only supplied evidence IDs and never invent IDs. "
        "Do not calculate, use outside knowledge, or make causal claims. Headline and "
        "reasoning must be qualitative: no digits, percentages, monetary or financial "
        "amounts, dates, number words, or repeated deterministic values. Evidence IDs such "
        "as E4 belong only in evidence_ids, never in prose. DecisionLens renders verified "
        "numbers separately. Return exactly focus, headline, reasoning, evidence_ids, and "
        "next_step with no extra fields."
    )


def _context_prompt(context: DecisionContext) -> str:
    context_payload = context.model_dump(mode="json")
    evidence = context_payload.pop("evidence")
    prompt = {
        "task": "Select a qualitative Decision Brief from verified evidence.",
        "allowed_evidence_ids": [item.id for item in context.evidence],
        "verified_evidence_meanings": evidence,
        "allowed_focus": [item.value for item in DecisionFocus],
        "allowed_next_step": [item.value for item in NextStepAction],
        "safe_deterministic_context": context_payload,
        "rules": [
            "Choose only supplied evidence IDs.",
            "Do not invent IDs.",
            "Do not calculate.",
            "Do not write numbers in headline or reasoning.",
            "Do not make causal claims.",
        ],
    }
    return json.dumps(prompt, separators=(",", ":"), sort_keys=True)


def _corrective_prompt(reason: str) -> str:
    return (
        f"The previous output was rejected by application validation: {reason}. "
        "Return a corrected JSON object. Use only allowed evidence IDs and actions. "
        "Headline and reasoning must contain no numbers, dates, amounts, percentages, "
        "number words, or evidence IDs. Do not calculate or make causal claims."
    )
