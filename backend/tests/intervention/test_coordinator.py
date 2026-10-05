from __future__ import annotations

import asyncio

import pytest

from intervention.coordinator import RoundCoordinator
from intervention.models import InterventionError


class FakeRuntime:
    def __init__(self, fail: bool = False):
        self.rounds: list[int] = []
        self.finish_reasons: list[str] = []
        self.fail = fail

    async def before_round(self, round_num: int):
        if self.fail:
            raise RuntimeError("Fake publish explosion")
        self.rounds.append(round_num)
        return []

    async def finish(self, reason: str):
        self.finish_reasons.append(reason)


@pytest.fixture
def fake_runtime():
    return FakeRuntime()


@pytest.mark.asyncio
async def test_fast_platform_waits_for_shared_boundary(fake_runtime):
    c = RoundCoordinator({"twitter", "reddit"}, fake_runtime)
    t = asyncio.create_task(c.before_round("twitter", 5))
    await asyncio.sleep(0.01)
    assert not t.done()
    await c.before_round("reddit", 5)
    await asyncio.wait_for(t, timeout=1.0)
    assert fake_runtime.rounds == [5]


@pytest.mark.asyncio
async def test_abort_releases_waiter(fake_runtime):
    c = RoundCoordinator({"twitter", "reddit"}, fake_runtime)
    t = asyncio.create_task(c.before_round("twitter", 5))
    await asyncio.sleep(0.01)
    assert not t.done()

    await c.abort("user canceled")
    with pytest.raises(InterventionError) as exc:
        await asyncio.wait_for(t, timeout=1.0)
    assert exc.value.code == "run_aborted"


@pytest.mark.asyncio
async def test_single_platform_no_extra_wait(fake_runtime):
    c = RoundCoordinator({"twitter"}, fake_runtime)
    await asyncio.wait_for(c.before_round("twitter", 1), timeout=1.0)
    assert fake_runtime.rounds == [1]


@pytest.mark.asyncio
async def test_publish_exception_releases_all():
    runtime = FakeRuntime(fail=True)
    c = RoundCoordinator({"twitter", "reddit"}, runtime)
    t1 = asyncio.create_task(c.before_round("twitter", 5))
    t2 = asyncio.create_task(c.before_round("reddit", 5))

    results = await asyncio.wait_for(
        asyncio.gather(t1, t2, return_exceptions=True),
        timeout=1.0,
    )
    assert all(isinstance(x, InterventionError) for x in results)


@pytest.mark.asyncio
async def test_round_mismatch_aborts(fake_runtime):
    c = RoundCoordinator({"twitter", "reddit"}, fake_runtime)
    t1 = asyncio.create_task(c.before_round("twitter", 5))
    await asyncio.sleep(0.01)
    t2 = asyncio.create_task(c.before_round("reddit", 6))

    results = await asyncio.wait_for(
        asyncio.gather(t1, t2, return_exceptions=True),
        timeout=1.0,
    )
    assert all(isinstance(x, InterventionError) for x in results)
    assert any(x.code == "round_mismatch" for x in results if isinstance(x, InterventionError))
