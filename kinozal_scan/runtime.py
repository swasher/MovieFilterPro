import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

executor = ThreadPoolExecutor(max_workers=4)

tasks: Dict[str, asyncio.Task] = {}
cancel_events: Dict[str, asyncio.Event] = {}
