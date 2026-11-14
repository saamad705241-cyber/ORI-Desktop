"""Small, testable helpers for buffering Gemini Live PCM before speaker writes."""
from __future__ import annotations

import asyncio


async def collect_audio_batch(
    queue: asyncio.Queue,
    first_chunk: bytes,
    *,
    target_bytes: int = 9600,
    max_wait_seconds: float = 0.16,
) -> bytes:
    """Collect up to about 200 ms of mono 24 kHz int16 audio.

    The short bounded wait gives the network stream a chance to deliver adjacent
    50 ms slices together. It smooths small delivery jitter without allowing an
    indefinite wait or adding a full sentence of latency.
    """
    target = max(1, int(target_bytes))
    batch = bytearray(first_chunk or b"")
    if len(batch) >= target or max_wait_seconds <= 0:
        return bytes(batch)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, float(max_wait_seconds))
    while len(batch) < target:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            chunk = await asyncio.wait_for(queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        if chunk:
            batch.extend(chunk)
    return bytes(batch)
