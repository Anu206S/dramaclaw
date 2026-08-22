"""Bounded parallel mapping for per-chunk LLM work.

Structured extraction runs one model call per source chunk, and a screenplay can
carry well over a hundred scenes.  Running them serially makes a build take
minutes of pure round-trip latency; running them all at once buries the gateway
and trips rate limits.  Both extremes are avoided by mapping with a fixed number
of slots in flight.

Results keep the input order regardless of completion order, because downstream
merging depends on chunk order to resolve ties deterministically.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_LIMIT = 6


async def map_bounded(
    items: Sequence[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    limit: int = DEFAULT_LIMIT,
    on_error: Callable[[T, BaseException], Any] | None = None,
) -> list[R | None]:
    """Run ``worker`` over ``items`` with at most ``limit`` calls in flight.

    A failing item yields ``None`` in its slot rather than cancelling the batch:
    one unparseable scene must not discard the analysis of every other scene.
    ``on_error`` is invoked for each failure so callers can record it against the
    chunk that produced it.
    """
    if not items:
        return []

    semaphore = asyncio.Semaphore(max(1, int(limit)))

    async def run(item: T) -> R | None:
        async with semaphore:
            try:
                return await worker(item)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                if on_error is not None:
                    on_error(item, exc)
                return None

    return list(await asyncio.gather(*(run(item) for item in items)))
