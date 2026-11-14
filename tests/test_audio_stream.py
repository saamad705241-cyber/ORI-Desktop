import asyncio

from core.audio_stream import collect_audio_batch


def test_collect_audio_batch_waits_for_adjacent_pcm_slices():
    async def run():
        queue = asyncio.Queue()
        queue.put_nowait(b"BBBB")
        batch = await collect_audio_batch(
            queue, b"AAAA", target_bytes=8, max_wait_seconds=0.05
        )
        return batch

    assert asyncio.run(run()) == b"AAAABBBB"


def test_collect_audio_batch_returns_partial_audio_after_bounded_wait():
    async def run():
        queue = asyncio.Queue()
        return await collect_audio_batch(
            queue, b"first", target_bytes=20, max_wait_seconds=0.01
        )

    assert asyncio.run(run()) == b"first"


def test_collect_audio_batch_does_not_wait_when_response_is_complete():
    async def run():
        queue = asyncio.Queue()
        return await collect_audio_batch(
            queue, b"last", target_bytes=32, max_wait_seconds=0
        )

    assert asyncio.run(run()) == b"last"
