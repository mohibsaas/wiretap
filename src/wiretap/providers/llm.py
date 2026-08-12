"""LiteLLM chat completions — keys from the environment."""

from __future__ import annotations

from typing import Any


def complete(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 512,
) -> str:
    import litellm  # heavy — import only when a completion is needed

    response: Any = litellm.completion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return str(response.choices[0].message.content or "").strip()
