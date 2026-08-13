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
# One softphone: the SIP client binds a fixed port and registers a single
# shared credential, so a second concurrent call collides.
_PSTN_CAP = 1


def provider_concurrency_cap(
    *,
    transport: str,
    platform: str | None = None,
) -> int:
    """Max recommended parallel dials for this agent target."""
    kind = (transport or "").lower().strip()
    if kind == "text":
        return _TEXT_CAP
    if kind == "pstn":
        return _PSTN_CAP
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
    kind = (transport or "").lower().strip()
    cap = provider_concurrency_cap(transport=transport, platform=platform)
    if kind == "pstn":
        # A registration limit rather than a provider quota, so --force cannot
        # lift it: parallel dials would fight over the same softphone.
        note = (
            f"clamped concurrency {req} → {_PSTN_CAP} for phone calls "
            f"(one softphone registration)"
            if req > _PSTN_CAP
            else None
        )
        return _PSTN_CAP, note
    if force or req <= cap:
        # Even with force, keep a hard sanity ceiling for text.
        if kind == "text":
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
