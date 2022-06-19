from tortoise.contrib import test
from tortoise.contrib.test import initializer, finalizer

from datetime import datetime
from metadata_processing.config import Config

from metadata_processing.worker import MetadataProcessing, TokenType
from metadata_processing.models import ItemToken, Holder, ItemTokenMetadata, MetadataStatus, PlaceToken, PlaceTokenMetadata


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

        invalid_ipfs_uri = "ipfs://bafktestinvalidtestinvalidtestinvalidtestinvalidtestinvalid"
        invalid_metadata = "ipfs://QmfXz1ibFh1B24RqFyv49AyMNeNqhuhP815aXzEYswcsSU"
        not_metadata = "ipfs://bafybeictsoehxf4zgdqrwppawr26l7l2bjpftftkdffgnnsfuroptfaoum/display.png"

        async def create_item(id, link):
            await ItemToken.create(
                id=id,
                royalties=10,
                minter=minter,
                metadata_uri=link,
                supply=50,
                level=1,
                timestamp=datetime.now())

        async def create_place(id, link):
            await PlaceToken.create(
                id=id,
                minter=minter,
                metadata_uri=link,
                level=1,
                timestamp=datetime.now())

        # Create invalid link
        await create_item(1, invalid_ipfs_uri)
        await create_place(1, invalid_ipfs_uri)

        # Create valid
        await create_item(2, "ipfs://bafkreif73mu4bhbjrxktsxmggxftzx4yfanaqsqmga3pacatwpwuitd37e")
        await create_place(2, "ipfs://bafkreih7y2mgq7akoorxv3asy4snlxkj6ns3eqblh43sb5comjvtletcwe")
        
        # Create invalid metadata
        await create_item(3, invalid_metadata)
        await create_place(3, invalid_metadata)

        # Create not metadata
        await create_item(4, not_metadata)
        await create_place(4, not_metadata)


    async def test_invalid_item_metadata_link(self):
        """Test invalid item metadata link"""
        with self.assertRaises(Exception):
            await self.processing.process_token((TokenType.Item, 1))
        self.assertEqual((await ItemToken.get(id=1)).metadata_status, MetadataStatus.Failed.value)


    async def test_invalid_place_metadata_link(self):
        """Test invalid place metadata link"""
        with self.assertRaises(Exception):
            await self.processing.process_token((TokenType.Place, 1))
        self.assertEqual((await PlaceToken.get(id=1)).metadata_status, MetadataStatus.Failed.value)


    async def test_valid_item_metadata(self):
        """Test valid item metadata"""
        await self.processing.process_token((TokenType.Item, 2))
        self.assertEqual((await ItemToken.get(id=2)).metadata_status, MetadataStatus.Valid.value)
        self.assertIsNotNone(await ItemTokenMetadata.get_or_none(id=2))


    async def test_valid_place_metadata(self):
        """Test valid place metadata"""
        await self.processing.process_token((TokenType.Place, 2))
        self.assertEqual((await PlaceToken.get(id=2)).metadata_status, MetadataStatus.Valid.value)
        self.assertIsNotNone(await PlaceTokenMetadata.get_or_none(id=2))


    async def test_invalid_item_metadata(self):
        """Test invalid place metadata"""
        await self.processing.process_token((TokenType.Item, 3))
        self.assertEqual((await ItemToken.get(id=3)).metadata_status, MetadataStatus.Invalid.value)


    async def test_invalid_place_metadata(self):
        """Test invalid place metadata"""
        await self.processing.process_token((TokenType.Place, 3))
        self.assertEqual((await PlaceToken.get(id=3)).metadata_status, MetadataStatus.Invalid.value)


    async def test_not_item_metadata(self):
        """Test not place metadata"""
        await self.processing.process_token((TokenType.Item, 4))
        self.assertEqual((await ItemToken.get(id=4)).metadata_status, MetadataStatus.Invalid.value)


    async def test_not_place_metadata(self):
        """Test not place metadata"""
        await self.processing.process_token((TokenType.Place, 4))
        self.assertEqual((await PlaceToken.get(id=4)).metadata_status, MetadataStatus.Invalid.value)
