from tortoise.contrib import test
from tortoise.contrib.test import initializer, finalizer

from datetime import datetime
from metadata_processing.config import Config

from metadata_processing.worker import MetadataProcessing, MetadataType
from metadata_processing.models import ItemToken, Holder, MetadataStatus, PlaceToken, Contract


class TestMetadataProcessing(test.TruncationTestCase):
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
        await self.processing.shutdown()
        await super(TestMetadataProcessing, self).asyncTearDown()

    async def create_test_db(self):
        minter = await Holder.create(address="minter")
        self.place_contract = await Contract.create(address="placecontract", metadata_uri="ipfs://bafkreibx3zte37b2xtfqjqbyko3hen4xtjqbxjvveakq3bexl5dbkyajg4", level=0, timestamp=0)
        self.item_contract = await Contract.create(address="itemcontract", metadata_uri="ipfs://bafkreiadopyojdbj7jyjhzacbxoweoxd5t3afadrnmp3nzkyodsqw4xqam", level=0, timestamp=0)

        invalid_ipfs_uri = "ipfs://bafktestinvalidtestinvalidtestinvalidtestinvalidtestinvalid"
        invalid_metadata = "ipfs://QmfXz1ibFh1B24RqFyv49AyMNeNqhuhP815aXzEYswcsSU"
        not_metadata = "ipfs://bafybeictsoehxf4zgdqrwppawr26l7l2bjpftftkdffgnnsfuroptfaoum/display.png"

        async def create_item(id, link):
            await ItemToken.create(
                transient_id=id,
                contract=self.item_contract,
                token_id=id,
                royalties=10,
                minter=minter,
                metadata_uri=link,
                supply=50,
                level=1,
                timestamp=datetime.now())

        async def create_place(id, link):
            await PlaceToken.create(
                transient_id=id,
                contract=self.place_contract,
                token_id=id,
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
        await self.processing.process_metadata((MetadataType.Item, 1))
        item_token: ItemToken = await ItemToken.get(transient_id=1).prefetch_related("metadata")
        self.assertEqual(item_token.metadata_status, MetadataStatus.Failed.value)
        self.assertIsNone(item_token.metadata)


    async def test_invalid_place_metadata_link(self):
        """Test invalid place metadata link"""
        await self.processing.process_metadata((MetadataType.Place, 1))
        place_token: PlaceToken = await PlaceToken.get(transient_id=1).prefetch_related("metadata")
        self.assertEqual(place_token.metadata_status, MetadataStatus.Failed.value)
        self.assertIsNone(place_token.metadata)


    async def test_invalid_contract_metadata_link(self):
        """Test invalid contract metadata link"""
        await self.processing.process_metadata((MetadataType.Contract, self.item_contract.address))
        contract: Contract = await Contract.get(address=self.item_contract.address).prefetch_related("metadata")
        self.assertEqual(contract.metadata_status, MetadataStatus.Failed.value)
        print(contract.metadata)
        print(contract.metadata_status)
        print(contract.metadata_uri)
        self.assertIsNone(contract.metadata)


    async def test_valid_item_metadata(self):
        """Test valid item metadata"""
        await self.processing.process_metadata((MetadataType.Item, 2))
        item_token: ItemToken = await ItemToken.get(transient_id=2).prefetch_related("metadata")
        self.assertEqual(item_token.metadata_status, MetadataStatus.Valid.value)
        self.assertIsNotNone(item_token.metadata)


    async def test_valid_place_metadata(self):
        """Test valid place metadata"""
        await self.processing.process_metadata((MetadataType.Place, 2))
        place_token: PlaceToken = await PlaceToken.get(transient_id=2).prefetch_related("metadata")
        self.assertEqual(place_token.metadata_status, MetadataStatus.Valid.value)
        self.assertIsNotNone(place_token.metadata)


    async def test_valid_contract_metadata(self):
        """Test valid contract metadata"""
        await self.processing.process_metadata((MetadataType.Contract, self.place_contract.address))
        contract: Contract = await Contract.get(address=self.place_contract.address).prefetch_related("metadata")
        self.assertEqual(contract.metadata_status, MetadataStatus.Valid.value)
        self.assertIsNotNone(contract.metadata)


    async def test_invalid_item_metadata(self):
        """Test invalid place metadata"""
        await self.processing.process_metadata((MetadataType.Item, 3))
        item_token: ItemToken = await ItemToken.get(transient_id=3).prefetch_related("metadata")
        self.assertEqual(item_token.metadata_status, MetadataStatus.Invalid.value)
        self.assertIsNone(item_token.metadata)


    async def test_invalid_place_metadata(self):
        """Test invalid place metadata"""
        await self.processing.process_metadata((MetadataType.Place, 3))
        place_token: PlaceToken = await PlaceToken.get(transient_id=3).prefetch_related("metadata")
        self.assertEqual(place_token.metadata_status, MetadataStatus.Invalid.value)
        self.assertIsNone(place_token.metadata)


    async def test_not_item_metadata(self):
        """Test not item metadata"""
        await self.processing.process_metadata((MetadataType.Item, 4))
        item_token: ItemToken = await ItemToken.get(transient_id=4).prefetch_related("metadata")
        self.assertEqual(item_token.metadata_status, MetadataStatus.Invalid.value)
        self.assertIsNone(item_token.metadata)


    async def test_not_place_metadata(self):
        """Test not place metadata"""
        await self.processing.process_metadata((MetadataType.Place, 4))
        place_token: PlaceToken = await PlaceToken.get(transient_id=4).prefetch_related("metadata")
        self.assertEqual(place_token.metadata_status, MetadataStatus.Invalid.value)
        self.assertIsNone(place_token.metadata)
