import asyncio
from datetime import date

from .runtime import executor, tasks, cancel_events
from .parse import kinozal_scan


async def start_scan_task(task_id: str, start_page: int, scan_to_date: date, user):
    cancel_event = asyncio.Event()
    cancel_events[task_id] = cancel_event

    loop = asyncio.get_running_loop()

    async def runner():
        try:
            return await loop.run_in_executor(
                executor,
                kinozal_scan,
                start_page,
                scan_to_date,
                user,
                cancel_event,
            )
        finally:
            # cleanup
            cancel_events.pop(task_id, None)
            tasks.pop(task_id, None)

    task = asyncio.create_task(runner())
    tasks[task_id] = task
