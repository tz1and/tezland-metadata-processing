import asyncio
from tortoise.contrib import test

from metadata_processing.task_pool import TaskPool


class TestTaskPool(test.IsolatedTestCase):
    async def throw_on_call(self):
        await asyncio.sleep(0.1)
        raise Exception('This fails.')

    async def test_pool_failure(self):
        """Make sure that TaskPool task fails properly"""
        task_pool = TaskPool(1)
        pending_tasks = 0

        def decrementPending(f):
            nonlocal pending_tasks
            pending_tasks -= 1

        fut = task_pool.submit(asyncio.create_task(self.throw_on_call()))
        fut.add_done_callback(decrementPending)
        pending_tasks += 1

        try:
            await fut
        except:
            pass
        else:
            raise Exception("Task should fail")
        finally:
            await task_pool.join()

        self.assertEqual(pending_tasks, 0, "pending_tasks isn't 0")
