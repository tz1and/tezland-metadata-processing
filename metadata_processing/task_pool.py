import asyncio
from asyncio.queues import Queue
import logging

TERMINATOR = object()


class TaskPool(object):
    def __init__(self, num_workers):
        self.tasks = Queue()
        self.workers: list[asyncio.Task] = []
        for _ in range(num_workers):
            # TODO: use create_task?
            worker = asyncio.ensure_future(self.worker())
            self.workers.append(worker)


    async def worker(self):
        while True:
            future: asyncio.Future
            task: asyncio.Task
            future, task = await self.tasks.get()

            if task is TERMINATOR:
                break

            # If wait_for fails, set exception
            try:
                result = await asyncio.wait_for(task, None)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

            if future.cancelled():
                return


    def submit(self, task):
        future = asyncio.Future()
        self.tasks.put_nowait((future, task))
        return future


    def cancel_all(self):
        for w in self.workers:
            w.cancel()


    async def join(self):
        for _ in self.workers:
            self.tasks.put_nowait((None, TERMINATOR))

        await asyncio.gather(*self.workers, return_exceptions=True)
