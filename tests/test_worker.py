import asyncio
import unittest
from tortoise.contrib import test
from tortoise.contrib.test import initializer, finalizer

from datetime import datetime
from metadata_processing.config import Config
from metadata_processing.task_pool import TaskPool

from metadata_processing.worker import MetadataProcessing, TokenType
from metadata_processing.models import ItemToken, Holder, PlaceToken


class TestMetadataProcessing(test.TestCase):
    @classmethod
    def setUpClass(cls):
        initializer(['metadata_processing.models'])

    @classmethod
    def tearDownClass(cls):
        finalizer()

    async def asyncSetUp(self):
        await super(TestMetadataProcessing, self).asyncSetUp()
        self.config = Config('test')
        self.processing = MetadataProcessing(self.config)
        await self.processing.init()
        await self.create_test_db()

    async def asyncTearDown(self):
        await super(TestMetadataProcessing, self).asyncTearDown()
        await self.processing.shutdown()

    async def create_test_db(self):
        minter = await Holder.create(address="minter")

        await ItemToken.create(
            id=1,
            royalties=10,
            minter=minter,
            metadata_uri="ipfs://ssssss",
            supply=50,
            level=1,
            timestamp=datetime.now())

        await ItemToken.create(
            id=2,
            royalties=10,
            minter=minter,
            metadata_uri="ipfs://bafkreif73mu4bhbjrxktsxmggxftzx4yfanaqsqmga3pacatwpwuitd37e",
            supply=50,
            level=1,
            timestamp=datetime.now())

        await PlaceToken.create(
            id=1,
            minter=minter,
            metadata_uri="ipfs://ssssss",
            level=1,
            timestamp=datetime.now())

        await PlaceToken.create(
            id=2,
            minter=minter,
            metadata_uri="ipfs://bafkreih7y2mgq7akoorxv3asy4snlxkj6ns3eqblh43sb5comjvtletcwe",
            level=1,
            timestamp=datetime.now())

    async def test_valid_item_metadata(self):
        await self.processing.process_token((TokenType.Item, 2))

    async def test_valid_place_metadata(self):
        await self.processing.process_token((TokenType.Place, 2))

    @test.expectedFailure
    async def test_invalid_item_metadata_link(self):
        await self.processing.process_token((TokenType.Item, 1))

    @test.expectedFailure
    async def test_invalid_place_metadata_link(self):
        await self.processing.process_token((TokenType.Place, 1))

    async def test_pool_failure(self):
        """Make sure that TaskPool task fails properly."""
        print("Testing TaskPool")
        task_pool = TaskPool(1)
        pending_tasks = 0

        def decrementPending(f):
            nonlocal pending_tasks
            pending_tasks -= 1

        fut = task_pool.submit(asyncio.create_task(self.processing.process_token((TokenType.Item, 1))))
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

        assert pending_tasks == 0, "pending_tasks isn't 0"
