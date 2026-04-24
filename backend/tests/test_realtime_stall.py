"""Tests for the listener's stall watchdog."""
import asyncio

import pytest

from app.realtime.listener import next_head


@pytest.mark.asyncio
async def test_next_head_returns_value_when_available():
    q: asyncio.Queue = asyncio.Queue()
    await q.put({"number": "0x1"})
    got = await next_head(q, timeout=1.0)
    assert got == {"number": "0x1"}


@pytest.mark.asyncio
async def test_next_head_returns_none_on_stall():
    q: asyncio.Queue = asyncio.Queue()
    # Nothing is ever put on the queue — simulates a zombie WS that stopped
    # delivering messages. After the timeout we should get None back (which
    # the run loop uses as the signal to reconnect).
    got = await next_head(q, timeout=0.05)
    assert got is None


@pytest.mark.asyncio
async def test_next_head_wakes_up_once_data_arrives():
    q: asyncio.Queue = asyncio.Queue()

    async def produce_after_delay():
        await asyncio.sleep(0.02)
        await q.put({"number": "0xa"})

    asyncio.create_task(produce_after_delay())
    got = await next_head(q, timeout=0.5)
    assert got == {"number": "0xa"}
