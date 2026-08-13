"""LiteLLM chat completions — keys from the environment.

Async is the default for simulation/judge so concurrent evals can
overlap on the event loop. Sync ``complete`` remains for one-shot CLI
paths (import/generate) that are not under asyncio.
"""

from __future__ import annotations

from typing import Any


async def acomplete(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 512,
) -> str:
    import litellm  # heavy — import only when a completion is needed

    response: Any = await litellm.acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return str(response.choices[0].message.content or "").strip()


def complete(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 512,
) -> str:
    """Blocking completion for sync CLI helpers (not used mid-call)."""
    import litellm

    response: Any = litellm.completion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return str(response.choices[0].message.content or "").strip()
