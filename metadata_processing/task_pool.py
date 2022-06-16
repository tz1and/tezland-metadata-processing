import asyncio
from asyncio.queues import Queue
import logging

TERMINATOR = object()


class TaskPool(object):
    def __init__(self, num_workers):
        self.tasks = Queue()
        self.workers = []
        for _ in range(num_workers):
            worker = asyncio.ensure_future(self.worker())
            self.workers.append(worker)

    async def worker(self):
        while True:
            future, task = await self.tasks.get()
            if task is TERMINATOR:
                break
            result = await asyncio.wait_for(task, None)
            future.set_result(result)

    def submit(self, task):
        future = asyncio.Future()
        self.tasks.put_nowait((future, task))
        return future

    async def join(self):
        for _ in self.workers:
            self.tasks.put_nowait((None, TERMINATOR))
        await asyncio.gather(*self.workers)
