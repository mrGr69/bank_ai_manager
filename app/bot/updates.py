from __future__ import annotations

import asyncio
from collections import deque

_MAX_SEEN = 500
_seen: set[int] = set()
_order: deque[int] = deque()
_bg_tasks: set[asyncio.Task] = set()


def remember_update(update_id: int | None) -> bool:
    """True if this Telegram update was not seen yet."""
    if update_id is None:
        return True
    uid = int(update_id)
    if uid in _seen:
        return False
    _seen.add(uid)
    _order.append(uid)
    while len(_order) > _MAX_SEEN:
        _seen.discard(_order.popleft())
    return True


def spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task
