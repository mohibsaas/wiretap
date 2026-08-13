"""Provider-aware concurrency limits for live dials.

Retell/Vapi/etc. web calls share LiveKit (or similar) rooms. High parallel
dials produce ConnectionTimeout / stream-closed storms and empty eval batches.
Clamp by default; allow explicit override when the user knows their quota.
"""

from __future__ import annotations

# Soft caps for live voice platforms (simultaneous web/WebRTC dials).
# Text / local stubs are cheap — allow a higher ceiling.
_VOICE_CAPS: dict[str, int] = {
    "retell": 2,
    "vapi": 2,
    "elevenlabs": 2,
    "livekit": 2,
    "synthflow": 2,
    "bolna": 2,
    "bland": 2,
}
_DEFAULT_VOICE_CAP = 2
_TEXT_CAP = 32


def provider_concurrency_cap(
    *,
    transport: str,
    platform: str | None = None,
) -> int:
    """Max recommended parallel dials for this agent target."""
    if (transport or "").lower().strip() == "text":
        return _TEXT_CAP
    plat = (platform or "").lower().strip()
    return _VOICE_CAPS.get(plat, _DEFAULT_VOICE_CAP)


def resolve_concurrency(
    requested: int,
    *,
    transport: str,
    platform: str | None = None,
    force: bool = False,
) -> tuple[int, str | None]:
    """Return ``(effective, note)``.

    ``note`` explains clamping when the request exceeds the provider-safe cap.
    """
    req = max(1, int(requested))
    cap = provider_concurrency_cap(transport=transport, platform=platform)
    if force or req <= cap:
        # Even with force, keep a hard sanity ceiling for text.
        if (transport or "").lower().strip() == "text":
            return min(req, _TEXT_CAP), None
        if force and req > cap:
            return req, (
                f"forcing concurrency={req} above {platform or 'voice'} safe "
                f"cap of {cap} — expect connection timeouts if the provider rejects dials"
            )
        return req, None
    return cap, (
        f"clamped concurrency {req} → {cap} for "
        f"{(platform or 'voice').lower()} live dials "
        f"(use --force-concurrency to override)"
    )


__all__ = [
    "provider_concurrency_cap",
    "resolve_concurrency",
]
